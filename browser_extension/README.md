# MussasWidget Music Bridge

This Chrome extension sends the visible track rows from an open Spotify, YouTube,
YouTube Music, or SoundCloud queue/playlist to the local MussasWidget process.
It reads page text only; it does not read cookies, passwords, or account tokens.

## Install

1. Start MussasWidget with the music module enabled.
2. Open `chrome://extensions` and enable **Developer mode**.
3. Select **Load unpacked** and choose this `browser_extension` folder.
4. Open the service's queue or playlist in the active Chrome tab.
5. In the widget's music cover, open the playlist view.

The bridge listens only on `127.0.0.1:47832`. The extension transfers at most 100
visible entries. A queue that is not rendered by the website cannot be read
without that service's own API and authorization.
