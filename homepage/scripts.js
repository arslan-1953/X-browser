let config = { news: false, weather: false, city: "" };
const form = document.getElementById("form");
const newsWidget = document.getElementById("newsWidget");
const newsList = document.getElementById("news");
const weatherWidget = document.getElementById("weatherWidget");
const attribution = document.getElementById("attribution");
const faviconServiceUrl = (siteUrl) => `https://www.google.com/s2/favicons?sz=64&domain_url=${encodeURIComponent(siteUrl)}`;

document.querySelectorAll(".site-link[data-site-url]").forEach((link) => {
  const siteUrl = link.dataset.siteUrl;
  const favicon = link.querySelector("img");
  if (!favicon) return;
  favicon.addEventListener("error", () => favicon.remove(), { once: true });
  favicon.src = faviconServiceUrl(siteUrl);
});

const formatRelativeTime = (unixSeconds) => {
  const elapsed = Math.round(unixSeconds - Date.now() / 1000);
  const units = [["year", 31536000], ["month", 2592000], ["week", 604800], ["day", 86400], ["hour", 3600], ["minute", 60]];
  const [unit, seconds] = units.find(([, size]) => Math.abs(elapsed) >= size) || ["minute", 60];
  return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(Math.round(elapsed / seconds), unit);
};

const fetchJson = async (url) => {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json();
};

const showNews = async () => {
  newsWidget.hidden = false;
  document.getElementById("newsNotice").textContent = "Loading top stories...";
  try {
    const storyIds = await fetchJson("https://hacker-news.firebaseio.com/v0/topstories.json");
    const stories = await Promise.all(storyIds.slice(0, 6).map((id) => fetchJson(`https://hacker-news.firebaseio.com/v0/item/${id}.json`)));
    const fragment = document.createDocumentFragment();
    stories.filter(Boolean).forEach((story, index) => {
      const item = document.createElement("li");
      item.className = "story";
      const rank = document.createElement("span");
      rank.className = "story__rank";
      rank.textContent = String(index + 1).padStart(2, "0");
      const body = document.createElement("div");
      body.className = "story__body";
      const favicon = document.createElement("img");
      favicon.className = "story__favicon";
      favicon.alt = "";
      favicon.src = faviconServiceUrl(story.url || "https://news.ycombinator.com/");
      favicon.addEventListener("error", () => favicon.remove(), { once: true });
      const link = document.createElement("a");
      link.className = "story__title";
      link.href = story.url || `https://news.ycombinator.com/item?id=${story.id}`;
      link.textContent = story.title || "Untitled story";
      const meta = document.createElement("p");
      meta.className = "story__meta";
      meta.textContent = `${story.score || 0} points · ${story.descendants || 0} comments · ${formatRelativeTime(story.time)}`;
      const arrow = document.createElement("span");
      arrow.className = "story__arrow";
      arrow.textContent = "↗";
      item.append(rank, body, arrow);
      body.append(favicon, link, meta);
      fragment.appendChild(item);
    });
    newsList.replaceChildren(fragment);
    document.getElementById("newsNotice").textContent = stories.length ? "" : "No stories are available right now.";
  } catch (error) {
    document.getElementById("newsNotice").textContent = "Top stories are unavailable. Check your connection and try again later.";
  }
};

const weatherDescription = (code) => {
  if (code === 0) return "Clear sky";
  if ([1, 2, 3].includes(code)) return "Partly cloudy";
  if ([45, 48].includes(code)) return "Foggy";
  if ([51, 53, 55, 56, 57].includes(code)) return "Drizzle";
  if ([61, 63, 65, 66, 67, 80, 81, 82].includes(code)) return "Rain";
  if ([71, 73, 75, 77, 85, 86].includes(code)) return "Snow";
  if ([95, 96, 99].includes(code)) return "Thunderstorms";
  return "Current conditions";
};

const showWeather = async (city) => {
  weatherWidget.hidden = false;
  const notice = document.getElementById("weatherNotice");
  if (!city.trim()) {
    notice.textContent = "Choose a city in Settings to see its forecast.";
    return;
  }
  notice.textContent = "Loading forecast...";
  try {
    const place = await fetchJson(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(city)}&count=1&language=en&format=json`);
    const result = place.results && place.results[0];
    if (!result) throw new Error("No matching city");
    const forecast = await fetchJson(`https://api.open-meteo.com/v1/forecast?latitude=${result.latitude}&longitude=${result.longitude}&current=temperature_2m,relative_humidity_2m,weather_code&timezone=auto`);
    const current = forecast.current;
    document.getElementById("weatherPlace").textContent = [result.name, result.country].filter(Boolean).join(", ");
    document.getElementById("temperature").textContent = `${Math.round(current.temperature_2m)}°`;
    document.getElementById("weatherSummary").textContent = weatherDescription(current.weather_code);
    document.getElementById("weatherDetail").textContent = `${current.relative_humidity_2m}% humidity · ${forecast.current_units.temperature_2m}`;
    document.getElementById("weatherIcon").textContent = current.weather_code === 0 ? "☼" : "◌";
    notice.textContent = "";
  } catch (error) {
    notice.textContent = "Weather is unavailable for that city right now.";
  }
};

const updateClock = () => {
  const now = new Date();
  document.getElementById("clock").textContent = now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  document.getElementById("date").textContent = now.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
  document.getElementById("welcomeDate").textContent = now.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric", year: "numeric" });
  const hour = now.getHours();
  document.getElementById("greeting").textContent = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
};

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = form.search.value.trim();
  if (!query) return;
  window.location = `x-browser://search?payload=${encodeURIComponent(JSON.stringify({ query }))}`;
});

updateClock();
setInterval(updateClock, 30000);
window.setHomepageWallpaper = (wallpaper) => {
  if (wallpaper) document.body.style.setProperty("--homepage-wallpaper", `url("${wallpaper}")`);
};

window.configureHomepage = (settings) => {
  config = { ...config, ...settings };
  window.setHomepageWallpaper(config.wallpaper);
  if (config.news) showNews();
  if (config.weather) showWeather(config.city || "");
  if (config.news || config.weather) {
    attribution.hidden = false;
    attribution.textContent = [config.news && "Top stories by Hacker News", config.weather && "Weather by Open-Meteo"].filter(Boolean).join(" · ");
  }
};
