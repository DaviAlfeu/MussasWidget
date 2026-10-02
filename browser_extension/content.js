(() => {
  const hostname = location.hostname;
  const provider = hostname === "open.spotify.com"
    ? "spotify"
    : hostname === "music.youtube.com"
      ? "youtube_music"
      : hostname === "www.youtube.com"
        ? "youtube"
        : hostname === "soundcloud.com"
          ? "soundcloud"
          : null;

  if (!provider) return;

  const SELECTORS = {
    spotify: [
      '[data-testid="tracklist-row"]',
      ".main-trackList-row"
    ],
    youtube_music: [
      "ytmusic-player-queue-item",
      "ytmusic-responsive-list-item-renderer"
    ],
    youtube: [
      "ytd-playlist-panel-video-renderer",
      "ytd-playlist-video-renderer"
    ],
    soundcloud: [
      ".queue__items .trackItem",
      ".queue .trackList__item",
      ".trackList__item"
    ]
  };

  function textOf(element) {
    return (element?.innerText || element?.textContent || "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function firstText(root, selectors) {
    for (const selector of selectors) {
      const value = textOf(root.querySelector(selector));
      if (value) return value;
    }
    return "";
  }

  function readTrack(row) {
    let title = firstText(row, [
      '[data-testid="internal-track-link"]',
      ".song-title",
      ".title",
      ".trackItem__trackTitle",
      "a[href*='/track/']",
      "a[href*='watch?v=']",
      "[title]"
    ]);
    if (!title) return null;

    const artist = firstText(row, [
      '[data-testid="artist-name"]',
      ".byline",
      ".trackItem__username",
      "a[href*='/artist/']"
    ]);
    return { title: title.slice(0, 200), artist: artist.slice(0, 200) };
  }

  function collectTracks() {
    for (const selector of SELECTORS[provider]) {
      const rows = [...document.querySelectorAll(selector)];
      const tracks = [];
      const seen = new Set();
      for (const row of rows) {
        const track = readTrack(row);
        if (!track) continue;
        const key = `${track.title}\u0000${track.artist}`;
        if (seen.has(key)) continue;
        seen.add(key);
        tracks.push(track);
      }
      if (tracks.length) return tracks.slice(0, 100);
    }
    return [];
  }

  function scan() {
    const tracks = collectTracks();
    const heading = textOf(document.querySelector(
      "ytmusic-player-queue #queue-title, " +
      "[data-testid='queue-title'], " +
      ".queue__header, " +
      "ytd-playlist-panel-renderer #title"
    ));
    chrome.runtime.sendMessage({
      type: "playlist-snapshot",
      snapshot: {
        provider,
        listTitle: heading || document.title.slice(0, 200),
        tracks
      }
    }, () => {
      if (chrome.runtime.lastError) return;
    });
  }

  let scanTimer;
  const scheduleScan = () => {
    clearTimeout(scanTimer);
    scanTimer = setTimeout(scan, 300);
  };

  new MutationObserver(scheduleScan).observe(document.documentElement, {
    childList: true,
    subtree: true
  });
  window.setInterval(scan, 2000);
  scan();
})();
