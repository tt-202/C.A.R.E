# Care app

Next.js web app for caregiver + user. Deployed on Vercel; local:

```bash
cd app/care-app
npm install
cp .env.example .env   # fill in Firebase, Postgres, etc.
npm run dev
```

## What it’s for

- Sign in (Firebase)
- Meal schedule + 1-hour reminders
- Start / Done / Emergency stop
- Bite hold setting
- Meal history
- Live robot status (Firestore)

Robot motion itself is handled by `robot-worker` + `pi-server`, not this app.

## Robot bridge

```env
ROBOT_ID=care-01
NEXT_PUBLIC_ROBOT_ID=care-01
NEXT_PUBLIC_ROBOT_ENABLED=true
```

Meal reminders when the tab is closed: set `CRON_SECRET` and hit `/api/cron/meal-reminders` with EasyCron (or similar). Don’t put a frequent cron in `vercel.json` on the Hobby plan — Vercel will reject the deploy.
