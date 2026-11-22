# Kevin's check in a brand-new Codespace (about 30 minutes)

This is the one part of fix 8 (19 November 2026) that could not be proven on the build machine: a real
GitHub Codespace, built from `.devcontainer/devcontainer.json`, with Docker inside it. What was proven
on the build machine, and what was not, is in `docs/HANDOFF-overnight.md`.

You need a browser, signed in to GitHub. Nothing else. The branch below is
`overnight/fixes-and-phase6`; once that work is on `mvp/crypto-simple`, use that branch instead.
Please note the clock time at steps 4 and 6: how long each took is one of the things we want to know.

1. **Open the repository.** Go to https://github.com/isogeny-labs/prototype. Click the branch button
   (above the file list, on the left; it shows a branch name) and choose `overnight/fixes-and-phase6`.
   *You should see:* the button now shows that name.

2. **Make a new Codespace.** Click the green **Code** button, then the **Codespaces** tab, then
   **Create codespace on overnight/fixes-and-phase6**. If you already have Codespaces listed there,
   click the **+** at the top of that tab instead. Use a new one, not an old one.
   *You should see:* a new browser tab opens.

3. **Allow it to read Otto.** The new tab shows "This codespace is requesting additional permissions"
   and names `isogeny-labs/otto`. Click **Authorize and continue**.
   *You should see:* "Setting up your codespace".
   *If there is no such page:* go on. Step 6 shows whether Otto could be read.

4. **Wait for the editor.** GitHub now builds the Codespace from the image the repository names. This
   is slower than before; expect several minutes.
   *You should see, at the end:* the editor, with the files on the left and a **Terminal** at the bottom
   whose last line ends in `$`.
   *If you see a red error box or the words "recovery mode":* press F1, type `creation log`, choose
   **Codespaces: View Creation Log**, copy the last 50 lines and send them. Stop here.

5. **Check the four tools.** Click in the terminal. Type each line and press Enter after each:

   ```
   python3.12 --version
   node --version
   git lfs version
   docker info --format '{{.ServerVersion}}'
   ```

   *You should see four answers, in this order:* `Python 3.12.` and a number; `v22.` and a number; a line
   that starts with `git-lfs/`; a version number such as `29.9.3` (that is Docker).
   *If an answer says "command not found", or the last one says "Cannot connect to the Docker daemon":*
   copy the four answers and send them. You can still go on.

6. **Start the app.** Type `./run-demo.sh` and press Enter. This first run is the long one.
   *You should see these lines appear, one after the other:*
   - `== Setting up Python (first run only, about a minute)`
   - `== Installing the backend packages`
   - `== Building the screens (first run, or after a change)`
   - `Fetching Adam's Otto harness at its pinned commit ...` and then `Otto harness: ready`
   - `== Checking isolated mode (Docker)`, then many lines that start with "Downloading" or "Building",
     and at the end `Isolated mode: ready.`
   - `== Isogeny Evidence Lab is starting`

   *If it stops with a line that starts `Could not start:`* copy that line and send it. Stop here.
   *If it says `Otto harness: missing`:* the app still starts. Copy the lines about Otto and send them.
   *If it says `Isolated mode: not ready` or `Isolated mode could not be prepared`:* the app still
   starts, in demo mode. Copy everything from `== Checking isolated mode (Docker)` down and send it.

7. **Open the app.** A small box appears at the bottom right: "Your application running on port 8000 is
   available". Click **Open in Browser**. If the box is gone: click the **Ports** tab (next to
   Terminal), move the mouse over the row with 8000 and click the globe icon. A second box for port
   8443 may appear; ignore it. Do not type the address the script prints (`http://127.0.0.1:8000`)
   into your own browser: that address is inside the Codespace.
   *You should see:* a new tab with the app, asking you to create a password.
   *If the tab says "Invalid host header", shows an error, or stays empty:* take a screenshot and send
   it.

8. **Go in.** Create a password (8 characters or more; it is for this Codespace only). Click
   **Load demo projects**.
   *You should see:* the Projects page with the demo projects.

9. **Read what the app says about itself.**
   - At the top of the app, a small label reads **Isolated mode** (not **Demo mode**).
   - Click **Settings** in the sidebar. It shows the sentence "Isolated mode: our demo software runs in
     a locked-down container with no network." and, under Otto, "Otto harness: version 0.1.0, commit
     aa4a6fd (pinned)."

   *If the label reads **Demo mode**, or Settings says "Otto is not installed on this computer":* copy
   the sentence and send it.

10. **Stop and start again.** Go back to the Codespace tab. Click in the terminal and press Ctrl+C.
    Then type `./run-demo.sh` again.
    *You should see:* the app starts again in well under a minute, without the Python, packages and
    screens lines. Press Ctrl+C again.

11. **One last look.** Type `git status --short` and press Enter.
    *You should see:* nothing.
    *If it prints a line with `.devcontainer/devcontainer-lock.json`:* that is harmless (GitHub's tool
    wrote the same fingerprints into a file of its own). Copy the line and send it; the next session
    adds the file.

12. **Send back:** the minutes for step 4 and for step 6, and either "all as described" or the texts
    asked for above. Then, so the Codespace does not keep costing money: open
    https://github.com/codespaces, click the three dots next to it and choose **Delete**.

## What each step proves that the build machine could not

- Step 4: the three add-ons (Node.js 22, Docker inside the Codespace, Git LFS) install on the image.
- Step 5: Node 22, Git LFS and Docker are really there.
- Step 6: Otto is fetched with GitHub's permission, and the Docker test images are prepared inside
  the Codespace.
- Step 7: GitHub's port forwarding reaches the app.
- Step 9: isolated mode.
- Step 11: whether GitHub writes a lock file.

## If step 4 fails on the add-ons

The add-ons are named by fingerprint (`ghcr.io/devcontainers/features/node@sha256:…`). The Dev
Containers command-line tool accepts that form (tried with versions 0.80.0, 0.89.0 and 0.90.0). If
GitHub's Codespaces does not, the fallback is to name them by version (`…/node:2`,
`…/docker-in-docker:4`, `…/git-lfs:1`) with a committed `.devcontainer/devcontainer-lock.json` that
holds the same fingerprints. `backend/tests/test_devcontainer.py` then needs its pattern changed.
