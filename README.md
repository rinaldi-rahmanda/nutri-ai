# nutri-ai

A Telegram bot that logs what you eat. Send it a photo of your food; it works
out what is on the plate, estimates the nutrition, and saves it to a Google
Sheet with the date, time, mealtime and who ate it.

## How it works

```
Telegram message ──> analyzer.py ──> nutrition.py ──> storage/ ──> reply
(photo, caption)     Claude: foods    USDA dataset:    Google Sheets
                     + grams          values per food  (or SQLite)
```

1. **analyzer.py**: Claude looks at the photo and caption and lists each food
   with a portion in grams. It also reads the caption for who ate it and which
   mealtime it was.
2. **nutrition.py**: each food is looked up in USDA FoodData Central and scaled
   to the portion. If the dataset has no believable match (common for regional
   dishes), Claude's own estimate is used and the row is marked `estimate`.
3. **storage/**: one row per food item is saved. Rows of the same meal share a
   `meal_id`.

Defaults when the caption doesn't say: the person is `DEFAULT_USER`, and the
mealtime comes from the clock (04-11 breakfast, 11-15 lunch, 18-22 dinner,
otherwise snack).

## Setup

You need [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
uv sync
cp .env.example .env
```

Then fill in `.env`:

1. **Telegram bot**: message [@BotFather](https://t.me/BotFather), send
   `/newbot`, and copy the token into `TELEGRAM_BOT_TOKEN`.
2. **Claude API key**: create one at <https://console.anthropic.com> and put it
   in `ANTHROPIC_API_KEY`. This is the one paid part: each photo is one API call.
3. **USDA key** (optional, free): <https://fdc.nal.usda.gov/api-key-signup>.
   The built-in `DEMO_KEY` works but allows only about 30 lookups an hour.
4. **Google Sheet**:
   1. In the [Google Cloud console](https://console.cloud.google.com), create a
      project and enable the **Google Sheets API**.
   2. Under *IAM & Admin > Service Accounts*, create a service account, then
      *Keys > Add key > JSON*. Save the file as `google-credentials.json` in
      this folder.
   3. Create a spreadsheet and share it (Editor) with the service account's
      email address (`...@...iam.gserviceaccount.com`).
   4. Copy the id from the spreadsheet URL (the part between `/d/` and `/edit`)
      into `GOOGLE_SHEET_ID`.

   To try the bot before doing this, set `STORAGE_PROVIDER=sqlite`.

Run it:

```bash
uv run python -m nutri_ai
```

Send `/start` to your bot. It replies with your chat id; put that in
`ALLOWED_CHAT_IDS` and restart so nobody else can use the bot (and your API key).

The bot must be running to answer, so leave it running on your computer or put
it on any small always-on machine. It uses long polling, so it needs no public
URL.

## Running on a Raspberry Pi

The bot only makes outbound connections (Telegram, Claude, USDA, Google), so
the Pi just needs ordinary internet. No port forwarding, public IP or domain.
If the Pi is off for a while, Telegram holds your messages for about 24 hours
and the bot logs them when it comes back, with the time you originally sent them.

1. **Get the code onto the Pi** (`git clone`, or copy the folder).
2. **Install uv** (it also installs Python 3.12 for you):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
   Open a new shell afterwards so `uv` is on your PATH.
3. **Install dependencies** (creates `.venv` in the project):
   ```bash
   cd ~/nutri-ai
   uv sync --no-dev
   ```
4. **Copy your secrets.** They are gitignored, so copy them from your computer:
   ```bash
   scp .env google-credentials.json pi@<pi-address>:~/nutri-ai/
   ```
   In `.env`, set `TIMEZONE` (for example `Asia/Jakarta`). The Pi is often on
   UTC, which would label your meals with the wrong mealtime otherwise.
5. **Try it once by hand**, then stop it with Ctrl+C:
   ```bash
   .venv/bin/python -m nutri_ai
   ```
6. **Run it as a service** so it starts on boot and restarts after a crash.
   Edit [deploy/nutri-ai.service](deploy/nutri-ai.service) first if your
   username is not `pi` or the project is not in `/home/pi/nutri-ai`.
   ```bash
   sudo cp deploy/nutri-ai.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now nutri-ai
   ```

Useful commands:

```bash
systemctl status nutri-ai       # is it running?
journalctl -u nutri-ai -f       # live logs
sudo systemctl restart nutri-ai # after changing .env or updating the code
```

With `STORAGE_PROVIDER=sheets` the bot writes nothing to the SD card except
logs, which is easier on it than a local database.

## Using it

- Send a photo. Optional caption: `dinner for Sarah`, `I only ate half`.
- Or describe a meal in text: `2 fried eggs and a slice of toast`.
- `/today [person]`: today's intake by mealtime.
- `/week [person]`: last 7 days, daily average and average per mealtime.
- `/undo`: remove the last meal logged from this chat.

## The sheet

The bot creates a `meals` worksheet with these columns:

`meal_id, timestamp, date, time, meal_type, person, food, grams, calories,
protein_g, carbs_g, fat_g, fiber_g, sugar_g, sodium_mg, source, note`

`date` is separate from `timestamp` so you can filter or pivot by day, mealtime
or person directly in Sheets (for example a pivot table with `date` as rows,
`meal_type` as columns and SUM of `calories` as values).

## Switching database

Everything goes through the `MealStore` interface in
[nutri_ai/storage/base.py](nutri_ai/storage/base.py) (three methods:
`add_entries`, `get_entries`, `delete_meal`). To add a provider:

1. Write a `MealStore` subclass in `nutri_ai/storage/`
   ([sqlite.py](nutri_ai/storage/sqlite.py) is a 40-line example).
2. Register it in `PROVIDERS` in [factory.py](nutri_ai/storage/factory.py).
3. Set `STORAGE_PROVIDER` to its name.

## Tests

```bash
uv run pytest
```
