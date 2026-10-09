# Deploy SafeWalk to Vercel

1. Upload this project to a GitHub repository. Include `app/`, `demo_data/`,
   `main.py`, `build.py`, `requirements.txt`, and `vercel.json`. Keep `.env`,
   `.venv`, and `instance` out of the repository.
2. Create a hosted PostgreSQL database (for example, through Vercel Marketplace).
   Copy its PostgreSQL connection string with SSL enabled.
3. In Vercel, choose **Add New > Project** and import your repository.
   Set the Root Directory to the folder containing `vercel.json`.
   Select Flask if it is not detected. Leave Output Directory unset.
4. Add these environment variables for Production and Preview:

   | Variable | Value |
   | --- | --- |
   | `FLASK_SECRET_KEY` | A stable random secret of at least 32 characters |
   | `GEOAPIFY_API_KEY` | Your Geoapify API key |
   | `DATABASE_URL` | Hosted PostgreSQL URL, such as `postgresql://USER:PASSWORD@HOST/DB?sslmode=require` |
   | `COOKIE_SECURE` | `true` |

   Generate a secret locally with:
   `python -c "import secrets; print(secrets.token_hex(32))"`.
   Enter credentials in Vercel settings, not in source files.
5. Click **Deploy**. Vercel serves `main.py` as the Flask entry point.
   The build copies CSS and JavaScript into `public/static/`. The CSV demo
   files, optional pre-trained Joblib model artifact, metadata, and templates
   are included in the function bundle.
6. Open `/health`, then test location search, route scores, and submitting a
   report. Refresh the page and confirm the report is retained.

Tables are not created automatically on Vercel. Provision the existing application
schema through a reviewed schema process. Existing local SQLite records are not
copied to PostgreSQL. See [synthetic lighting and ML details](LIGHTING.md).
The production dependencies include scikit-learn and its numeric runtime so a
previously trained, trusted artifact can be loaded in Flask without training
during a request. Do not deploy until the model artifact is trained in a
compatible environment and included in the release; until then, cards use the
explicit synthetic-data fallback.

To create an admin, run the existing `create-admin` Flask command locally with
`DATABASE_URL` set to the hosted database and dependencies installed:
`python -m flask --app main create-admin`.

Vercel functions have no durable local SQLite storage. This project requires
PostgreSQL when running on Vercel. The app's request limiter is per process;
use Vercel's firewall rate limits for limits shared across function instances.

After changing environment variables, redeploy. Keep `FLASK_SECRET_KEY` stable
so existing browser sessions retain access to their reports.

Official guide: https://vercel.com/docs/frameworks/backend/flask
