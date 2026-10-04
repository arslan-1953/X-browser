import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from PyQt6.QtCore import QThread, pyqtSignal


class DownloadCancelled(Exception):
    pass


class DownloadWorker(QThread):
    progress_changed = pyqtSignal(int, int)
    status_changed = pyqtSignal(str)
    completed = pyqtSignal(bool, str)

    def __init__(self, url, output_path, task_id, parent=None, thread_count=4):
        super().__init__(parent)
        self.url = url
        self.output_path = output_path
        self.task_id = task_id
        self.thread_count = max(1, thread_count)
        self._resume_event = threading.Event()
        self._resume_event.set()
        self._cancel_event = threading.Event()
        self._progress_lock = threading.Lock()
        self._downloaded_bytes = 0

    def pause(self):
        self._resume_event.clear()

    def resume(self):
        self._resume_event.set()

    def cancel(self):
        self._cancel_event.set()
        self._resume_event.set()

    def run(self):
        try:
            if os.path.exists(self.output_path):
                raise FileExistsError(f"File already exists: {self.output_path}")

            file_size, supports_ranges = self._inspect_server()
            if supports_ranges and file_size:
                self._download_ranges(file_size)
            else:
                self._download_stream(file_size)

            self._check_cancelled()
            cleanup_warning = self._merge_parts()
            self.completed.emit(True, cleanup_warning)
        except DownloadCancelled:
            self._cleanup_parts()
            self.completed.emit(False, "Cancelled")
        except (OSError, requests.RequestException, ValueError) as error:
            self.completed.emit(False, self._error_with_cleanup(str(error) or error.__class__.__name__))
        except Exception as error:
            self.completed.emit(False, self._error_with_cleanup(f"Unexpected downloader error: {error}"))

    def _inspect_server(self):
        self.status_changed.emit("Connecting")
        file_size = 0
        session = requests.Session()
        headers = {"User-Agent": "XBrowser/2.0"}
        try:
            response = session.head(self.url, allow_redirects=True, timeout=(10, 20), headers=headers)
            if response.ok:
                file_size = int(response.headers.get("content-length", 0) or 0)
            response.close()
        except requests.RequestException:
            pass

        try:
            response = session.get(
                self.url,
                headers={**headers, "Accept-Encoding": "identity", "Range": "bytes=0-0"},
                allow_redirects=True,
                stream=True,
                timeout=(10, 20),
            )
            content_range = response.headers.get("Content-Range", "")
            match = re.fullmatch(r"bytes\s+0-0/(\d+)", content_range.strip(), re.IGNORECASE)
            supports_ranges = response.status_code == 206 and match is not None
            if supports_ranges:
                file_size = int(match.group(1))
            elif response.status_code == 200:
                file_size = int(response.headers.get("content-length", file_size) or file_size)
            elif response.status_code == 416 and file_size == 0:
                return 0, False
            else:
                response.raise_for_status()
            response.close()
            return file_size, supports_ranges
        finally:
            session.close()

    def _download_ranges(self, file_size):
        part_count = min(self.thread_count, file_size)
        base_size, extra_bytes = divmod(file_size, part_count)
        ranges = []
        start = 0
        for index in range(part_count):
            end = start + base_size + (1 if index < extra_bytes else 0) - 1
            ranges.append((index, start, end))
            start = end + 1
        with self._progress_lock:
            self._downloaded_bytes = sum(
                min(self._part_size(index), end - start + 1)
                for index, start, end in ranges
            )
        self.progress_changed.emit(self._downloaded_bytes, file_size)

        with ThreadPoolExecutor(max_workers=part_count) as executor:
            while True:
                self._wait_until_resumed()
                unfinished = [
                    item for item in ranges
                    if self._part_size(item[0]) < item[2] - item[1] + 1
                ]
                if not unfinished:
                    return

                futures = [executor.submit(self._download_range, index, start, end, file_size)
                           for index, start, end in unfinished]
                failure = None
                for future in as_completed(futures):
                    try:
                        future.result()
                    except DownloadCancelled:
                        raise
                    except Exception as error:
                        failure = error
                        self._cancel_event.set()
                        self._resume_event.set()
                        for pending in futures:
                            pending.cancel()
                        break
                if failure:
                    raise failure
                self._check_cancelled()
                if not self._resume_event.is_set():
                    self.status_changed.emit("Paused")
                    self._wait_until_resumed()
                    self.status_changed.emit("Downloading")

    def _download_range(self, index, start, end, file_size):
        part_path = self._part_path(index)
        expected_size = end - start + 1
        offset = os.path.getsize(part_path) if os.path.exists(part_path) else 0
        if offset >= expected_size:
            return
        position = start + offset
        response = requests.get(
            self.url,
            headers={
                "User-Agent": "XBrowser/2.0",
                "Accept-Encoding": "identity",
                "Range": f"bytes={position}-{end}",
            },
            stream=True,
            allow_redirects=True,
            timeout=(10, 20),
        )
        try:
            if response.status_code != 206:
                response.raise_for_status()
                raise requests.HTTPError("Server stopped supporting byte-range downloads.")
            content_range = response.headers.get("Content-Range", "")
            match = re.fullmatch(r"bytes\s+(\d+)-(\d+)/(\d+)", content_range.strip(), re.IGNORECASE)
            if not match or tuple(map(int, match.groups())) != (position, end, file_size):
                raise requests.HTTPError("Server returned an invalid byte range.")
            mode = "ab" if offset else "wb"
            bytes_written = offset
            with open(part_path, mode) as output:
                for data in response.iter_content(chunk_size=64 * 1024):
                    self._check_cancelled()
                    if not self._resume_event.is_set():
                        break
                    if data:
                        if bytes_written + len(data) > expected_size:
                            raise requests.HTTPError("Server sent more data than requested for this range.")
                        output.write(data)
                        bytes_written += len(data)
                        with self._progress_lock:
                            self._downloaded_bytes += len(data)
                            downloaded = self._downloaded_bytes
                        self.progress_changed.emit(min(downloaded, file_size), file_size)
            if self._resume_event.is_set() and not self._cancel_event.is_set() and bytes_written != expected_size:
                raise requests.ConnectionError("The server closed a byte range before all data arrived.")
        finally:
            response.close()

    def _download_stream(self, file_size):
        part_path = self._part_path("stream")
        with self._progress_lock:
            self._downloaded_bytes = os.path.getsize(part_path) if os.path.exists(part_path) else 0

        while True:
            self._wait_until_resumed()
            offset = os.path.getsize(part_path) if os.path.exists(part_path) else 0
            if file_size and offset >= file_size:
                return
            headers = {"User-Agent": "XBrowser/2.0"}
            headers["Accept-Encoding"] = "identity"
            if offset:
                headers["Range"] = f"bytes={offset}-"
            response = requests.get(
                self.url,
                headers=headers,
                stream=True,
                allow_redirects=True,
                timeout=(10, 20),
            )
            try:
                if offset and response.status_code == 206:
                    content_range = response.headers.get("Content-Range", "")
                    if not content_range.lower().startswith(f"bytes {offset}-"):
                        raise requests.HTTPError("Server returned an invalid resume range.")
                    mode = "ab"
                    skip_bytes = 0
                else:
                    response.raise_for_status()
                    mode = "wb" if not offset or response.status_code == 200 else "ab"
                    skip_bytes = offset if mode == "wb" and offset else 0
                    if mode == "wb" and offset:
                        with self._progress_lock:
                            self._downloaded_bytes = 0
                        self.progress_changed.emit(0, file_size)

                self.status_changed.emit("Downloading")
                with open(part_path, mode) as output:
                    for data in response.iter_content(chunk_size=64 * 1024):
                        self._check_cancelled()
                        if not self._resume_event.is_set():
                            break
                        if not data:
                            continue
                        if skip_bytes:
                            skipped = min(skip_bytes, len(data))
                            skip_bytes -= skipped
                            data = data[skipped:]
                            if not data:
                                continue
                        output.write(data)
                        with self._progress_lock:
                            self._downloaded_bytes += len(data)
                            downloaded = self._downloaded_bytes
                        self.progress_changed.emit(downloaded, file_size)
                if not self._resume_event.is_set():
                    self.status_changed.emit("Paused")
                    continue
                if file_size and os.path.getsize(part_path) != file_size:
                    raise requests.ConnectionError("The server closed the connection before the full file arrived.")
                return
            finally:
                response.close()

    def _part_path(self, index):
        return f"{self.output_path}.{self.task_id}.{index}.part"

    def _part_size(self, index):
        path = self._part_path(index)
        return os.path.getsize(path) if os.path.exists(path) else 0

    def _merge_parts(self):
        self.status_changed.emit("Merging file")
        temporary_path = f"{self.output_path}.{self.task_id}.tmp"
        part_paths = [
            self._part_path(index)
            for index in range(self.thread_count)
            if os.path.exists(self._part_path(index))
        ]
        if not part_paths:
            part_paths = [self._part_path("stream")]

        try:
            with open(temporary_path, "wb") as output:
                for part_path in part_paths:
                    with open(part_path, "rb") as part:
                        while True:
                            self._check_cancelled()
                            data = part.read(1024 * 1024)
                            if not data:
                                break
                            output.write(data)
            if os.path.exists(self.output_path):
                raise FileExistsError(f"File already exists: {self.output_path}")
            os.replace(temporary_path, self.output_path)
        finally:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
        cleanup_errors = self._cleanup_parts()
        return "; ".join(cleanup_errors)

    def _cleanup_parts(self):
        errors = []
        for index in range(self.thread_count):
            path = self._part_path(index)
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError as error:
                    errors.append(f"Could not remove temporary file {path}: {error}")
        stream_path = self._part_path("stream")
        if os.path.exists(stream_path):
            try:
                os.remove(stream_path)
            except OSError as error:
                errors.append(f"Could not remove temporary file {stream_path}: {error}")
        return errors

    def _error_with_cleanup(self, message):
        cleanup_errors = self._cleanup_parts()
        if cleanup_errors:
            return f"{message}; {'; '.join(cleanup_errors)}"
        return message

    def _wait_until_resumed(self):
        while not self._resume_event.wait(0.1):
            self._check_cancelled()
        self._check_cancelled()

    def _check_cancelled(self):
        if self._cancel_event.is_set():
            raise DownloadCancelled()
