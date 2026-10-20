# MussasWidget Music Bridge

This Chrome extension can send visible track rows from Spotify, YouTube,
YouTube Music, or SoundCloud to the local MussasWidget process. The music module
currently displays the playlist only on YouTube Music (`music.youtube.com`).
It reads visible page text and track links; it does not read cookies, passwords,
or account tokens.

## Install

1. Start MussasWidget with the music module enabled.
2. Open `chrome://extensions` and enable **Developer mode**.
3. Select **Load unpacked** and choose this `browser_extension` folder.
4. Open a queue or playlist on `music.youtube.com` in the active Chrome tab.
5. In the widget's music cover, open the playlist view.

The bridge listens only on `127.0.0.1:47832`. The extension transfers at most 100
visible entries. A queue that is not rendered by the website cannot be read
without that service's own API and authorization.

When a track URL is available, double-clicking it opens the YouTube Music track
in the default browser without moving the mouse. Without the extension, the
module can still read visible playlist rows through Windows UI Automation; track
selection then depends on the player exposing an accessible default action.
