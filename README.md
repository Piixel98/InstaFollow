# InstaFollow

InstaFollow is a modular Instagram automation tool built with Python and Playwright. It identifies users you follow who do not follow you back and provides an option to unfollow them automatically.

## Key Features

- **Automated Scanning**: Automatically collects your followers and following lists.
- **Comparison**: Identifies "non-followers" (people you follow but don't follow you back).
- **Session Persistence**: Saves cookies to avoid repeated logins and handle 2FA more easily.
- **Manual Confirmation**: Prompts for confirmation before proceeding with the unfollow process.
- **Stealth Mode**: Uses `playwright-stealth` and human-like delays to minimize detection risks.
- **Reporting**: Generates a `non_followers.txt` file with the list of identified users.
- **Desktop UI**: Dark PySide6 interface with English/Spanish UI language selection and detailed logs.

## Prerequisites

- **Python**: 3.11 or higher.
- **Poetry**: Dependency manager for Python.
- **Google Chrome**: The script uses your local Chrome installation.

## Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd InstaFollow
   ```

2. **Install dependencies using Poetry**:
   ```bash
   poetry install
   ```

3. **Install Playwright browsers**:
   ```bash
   poetry run playwright install chromium
   ```

## Configuration

Before running the script, update `config.py` with your environment values:

```python
INSTAGRAM = "https://www.instagram.com"
COOKIES_FILE = "cookies.json"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
```

- The desktop app asks for the Instagram handle to review in the `@instagram` field and stores it in local settings.
- `CHROME_PATH`: The absolute path to your Chrome executable.

## How to Run

1. **Run the desktop UI**:
   ```bash
   poetry run python gui.py
   ```

2. **Or run the console script**:
   ```bash
   poetry run python main.py
   ```

3. **Desktop UI workflow**:
   - Choose **Analyze account** / **Analizar cuenta** to collect followers and following accounts.
   - Choose **Unfollow** / **Dejar de seguir** to review the exported list and unfollow selected accounts.
   - Use **Config** to change the UI language, export file, and logs directory.
   - Use **Show browser** / **Ver navegador** to inspect the embedded Chrome session when needed.

## Desktop UI User Manual

### 1. Start the app

Run:

```bash
poetry run python gui.py
```

The app opens with a dark desktop interface. The top header contains the workflow selector, status badge, and options menu.

### 2. Select a workflow

Use the segmented selector in the header:

- **Analyze account / Analizar cuenta**: collects the target account's followers and following lists, compares them, and exports non-followers.
- **Unfollow / Dejar de seguir**: loads the exported non-followers file and lets you choose which accounts to unfollow.

The selected workflow is highlighted. The **Start / Iniciar** button runs the selected workflow.

### 3. Configure language, export and logs

Open the three-dot menu and click **Config**.

In the config dialog you can set:

- **Application language / Idioma de la aplicacion**: Spanish or English, shown with SVG flags.
- **Export file / Fichero de exportacion**: where the non-followers list is saved. Default: `non_followers.txt`.
- **Logs directory / Directorio de logs**: where detailed logs are written. Default: `logs/`.

Click **Save / Guardar** to apply the configuration.

### 4. Enter the target account

In the session form, fill **@instagram** with the Instagram username you want to review.

The value is saved locally in app settings. You do not need to edit `config.py` for this username.

### 5. Prepare the login session

If there is a valid `cookies.json`, the app locks the credentials fields and uses the saved session.

If there is no valid session:

1. Enter your Instagram login username and password.
2. Click **Save / Guardar**.
3. Click **Start / Iniciar**.
4. The app launches Chrome through Playwright and embeds it in the browser panel.

Credentials are kept in memory only. They are not written to disk.

### 6. Handle two-factor authentication

If Instagram asks for a security code, the app opens a non-blocking code dialog. The browser keeps running in the background while the dialog is open.

In the dialog:

- Enter the security code and click **Save / Guardar**.
- Use the eye button to show or hide the code.
- If the code does not arrive, wait for the countdown to finish. Then click **Recibir un codigo nuevo / Get a new code** to ask Instagram for a new code.

The resend action clicks Instagram's visible **Recibir un codigo nuevo** button inside the embedded browser.

### 7. Analyze account

With **Analyze account / Analizar cuenta** selected:

1. Click **Start / Iniciar**.
2. The app collects followers and following accounts.
3. The counters update as the process progresses.
4. Non-followers are exported to the configured export file.

Use **Export / Exportar** to open the generated file.

### 8. Unfollow selected accounts

With **Unfollow / Dejar de seguir** selected:

1. Make sure the export file exists.
2. Click **Start / Iniciar**.
3. Select the accounts you want to unfollow.
4. Use **View profile / Ver perfil** to inspect a profile before selecting it.
5. Confirm with **Unfollow / Dejar de seguir**.

After each successful unfollow, the user is removed from the export file so the list stays current.

### 9. Browser panel

Use **Show browser / Ver navegador** to display the embedded Chrome window.

Use **Hide browser / Ocultar navegador** to return to the session form. The browser can keep running while hidden.

### 10. Logs and output

The output panel shows user-visible events. Detailed logs are written to the configured logs directory.

Use the three-dot menu to:

- Open **Config**.
- Open detailed logs.
- Clear the visible output.

## Console Workflow

The console script remains available with:

```bash
poetry run python main.py
```

It asks for credentials, the target Instagram username, and 2FA codes directly in the terminal. The desktop UI is recommended for normal use.

## Build a Windows `.exe`

The application can be packaged with PyInstaller. The generated executable will use the values embedded in `config.py`, so update `INSTAGRAM`, `COOKIES_FILE`, and `CHROME_PATH` before building. If you change `config.py` later, rebuild the executable.

1. **Install the build dependencies**:
   ```powershell
   poetry add --group dev pyinstaller
   ```
   PyInstaller installs its Windows helper packages, including `pywin32-ctypes`, automatically.

2. **Build the executable**:
   ```powershell
   poetry run pyinstaller --noconfirm --clean --windowed --onefile --name InstaFollow --icon assets\instafollow.ico --add-data "assets;assets" --collect-all PySide6 gui.py
   ```

3. **Run the generated file**:
   ```powershell
   .\dist\InstaFollow.exe
   ```

Runtime files such as `cookies.json`, `non_followers.txt`, and timestamped files under `logs/` are created in the folder where you run the executable. Keep Chrome installed at the path configured in `CHROME_PATH`; this project launches your local Chrome instead of bundling a browser.

The desktop UI embeds only the Playwright-controlled Chrome window inside the app on Windows. If embedding fails, the browser is kept hidden instead of being shown as a separate window.

## Project Structure

- `main.py`: Entry point of the application.
- `gui.py`: Desktop UI entry point.
- `ui/`: PySide6 interface, worker thread, embedded-browser host, styles, and log bridge.
- `assets/`: Application icon and bundled UI assets.
- `browser.py`: Playwright browser and context setup with stealth mode.
- `config.py`: Global configuration and constants.
- `cookies.py`: Logic for saving and loading session cookies.
- `instagram.py`: Collects followers/following through Instagram's API, with DOM scrolling as fallback.
- `utils.py`: Logging setup and human-like delay functions.

## Disclaimer

This tool is for educational purposes only. Using automation on Instagram may violate their Terms of Service and could lead to account restrictions or bans. Use it at your own risk. Always use reasonable delays and avoid aggressive unfollowing.
