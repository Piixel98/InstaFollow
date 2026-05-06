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

Before running the script, update `config.py` with your information:

```python
USERNAME = "your_instagram_username"
INSTAGRAM = "https://www.instagram.com"
COOKIES_FILE = "cookies.json"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
```

- `USERNAME`: Your Instagram handle.
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

3. **Initial Login**:
   - If no valid cookies are found, a Chrome window will open.
   - Log in manually to your Instagram account.
   - Complete any Two-Factor Authentication (2FA) if required.
   - Once you are on your Instagram feed, return to the terminal and press **ENTER**.
   - Your session (cookies) will be saved for future runs.

4. **Process**:
   - The script will start collecting your followers and following lists (this may take some time depending on your account size).
   - It will display a list of users who don't follow you back.
   - A `non_followers.txt` file will be created.
   - You will be asked if you want to proceed with the unfollow process.
   - If you agree, the script will visit each profile and ask for confirmation before unfollowing.

## Build a Windows `.exe`

The application can be packaged with PyInstaller. The generated executable will use the values embedded in `config.py`, so update `USERNAME`, `INSTAGRAM`, `COOKIES_FILE`, and `CHROME_PATH` before building. If you change `config.py` later, rebuild the executable.

1. **Install PyInstaller in the Poetry environment**:
   ```powershell
   poetry add --group dev pyinstaller
   ```

2. **Build the executable**:
   ```powershell
   poetry run pyinstaller --noconfirm --clean InstaFollow.spec
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
- `scroll.py`: Advanced scrolling logic to collect all users from Instagram's dynamic lists.
- `unfollow.py`: Logic for visiting profiles and performing the unfollow action.
- `utils.py`: Logging setup and human-like delay functions.

## Disclaimer

This tool is for educational purposes only. Using automation on Instagram may violate their Terms of Service and could lead to account restrictions or bans. Use it at your own risk. Always use reasonable delays and avoid aggressive unfollowing.

