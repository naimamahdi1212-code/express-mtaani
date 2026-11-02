# Express Mtaani

Delivery marketplace for Nairobi: customers order food and products from local shops, the nearest
online rider accepts the order and delivers it, and the customer follows the rider live on a map.
An admin dashboard runs shops, products, riders and orders.

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                  # then edit .env (SECRET_KEY and GEOAPIFY_API_KEY)
flask --app wsgi init-db              # create the tables
flask --app wsgi create-admin         # asks for your admin email and password
flask --app wsgi seed-demo            # optional: 3 demo shops with sample products
flask --app wsgi run --debug
```

Open http://127.0.0.1:5000

**Upgrading from the first version?** The database layout changed. In development, stop the server,
delete the file `instance/express_mtaani.db`, and run the three commands above again.

## The three kinds of user

| Role | How they get an account | What they do |
|------|------------------------|--------------|
| Customer | Signs up at `/register` | Browses the home page, fills a cart (one shop per order), checks out, follows the order on a map |
| Rider | Signs up at `/rider/register`; an admin must approve them | Goes online, sees new orders from shops near them (nearest first), accepts one, delivers it |
| Admin | Created with `flask --app wsgi create-admin` (nobody can sign up as admin) | Dashboard, orders, products, shops, riders |

## How rider matching works

1. The rider opens `/rider`, taps **Go online** and allows location. Their position is sent every 8 seconds.
2. A rider is "online" only while that position is recent (default 2 minutes), so a closed phone drops out.
3. When a customer places an order, every online rider whose last position is within `NEARBY_RADIUS_KM`
   (default 6 km) of the **shop** sees it, nearest first. They see the shop and delivery area, not the customer's name or phone.
4. The first rider to tap **Accept** gets it. The database claim is atomic, so two riders can never both win.
5. A rider can hold one delivery at a time, and can **release** an order before pickup so someone else can take it.
6. Admins can also assign any approved rider by hand from the order page.

Delivery: accept, then **Picked up, start delivery**, then **Mark as delivered** (the rider confirms whether cash was collected).

## Payments

Cash on delivery only for now. A rider confirms cash when delivering; an admin can mark cash as received
for anything left unconfirmed. M-Pesa (Daraja) is the next step and is shown as "coming soon" at checkout.

## Map keys (Geoapify, free, no credit card)

1. Sign up at https://myprojects.geoapify.com and create a project.
2. Put the key in `.env` as `GEOAPIFY_API_KEY`.
3. Restrict it to your domains (`localhost`, `127.0.0.1`, and your live site) in the project settings.
4. The free plan has 3,000 credits per day and requires attribution (already shown on the map).

## Try the whole flow on one computer

1. Create an admin, run `seed-demo`, sign in at `/login` and look around `/admin/`.
2. In a private window sign up as a customer and place an order from the home page.
3. In another browser sign up as a rider at `/rider/register`, approve it from `/admin/riders`, sign in, tap **Go online**.
   (Rider positions come from your device's GPS. In Chrome you can fake one: DevTools, three dots, More tools, Sensors, Location.)
4. Accept the order. On the delivery page add `?sim=1` to the URL and click **Simulate a ride**.
   The rider dot moves on the customer's tracking page and on the admin live map.

## Things to know

- Browser GPS needs **HTTPS** (localhost is exempt). Tracking works only while the rider's page is open; the page asks the phone to keep the screen on.
- Flask needs a Python host (Render, Railway, PythonAnywhere, a VPS). Netlify and Vercel host static sites only.
- Passwords are hashed. Forms use CSRF tokens. All prices, delivery fees and totals are calculated on the server. Sign-in attempts are rate limited in memory (use Flask-Limiter + Redis when you run more than one server).
- Delivery fee is straight-line distance from shop to customer (`DELIVERY_BASE_FEE` + `DELIVERY_PER_KM` per started km, rounded up to 10).
- Set a strong `SECRET_KEY`, and `APP_ENV=production` on the live server (the app refuses to start in production with the default key).
- For PostgreSQL set `DATABASE_URL`, then use `flask db init / migrate / upgrade` (Flask-Migrate is wired in).
- Product pictures are image links (https) for now. File uploads are a later step.
- Tests: `python -m pytest`
- Static files (CSS, JavaScript, images) live in `public/static/` so Vercel can serve them from its CDN.

## Deploy: GitHub + Vercel + PostgreSQL

**Before you start.** Vercel's free Hobby plan is for personal, non-commercial use only. A site that earns delivery
fees needs the Pro plan. SQLite does not work on Vercel (files do not persist), so you need a hosted PostgreSQL database.

1. **Push to GitHub** (a private repository is best). Check `git status` first: `.env` must NOT be listed.
2. **Create a database.** In Vercel, open your project, Storage (or Marketplace), and add a Neon PostgreSQL database.
   It adds `DATABASE_URL` (or `POSTGRES_URL`) to your project's environment variables. Supabase also works.
3. **Import the repository** at vercel.com/new. Vercel finds `wsgi.py` and the Flask app by itself. No build command is needed.
4. **Set environment variables** (Project, Settings, Environment Variables):
   `APP_ENV=production`, `SECRET_KEY=<long random string>`, `GEOAPIFY_API_KEY=<your key>`.
   Optional: `NEARBY_RADIUS_KM`, `RIDER_FRESH_SECONDS`, `DELIVERY_BASE_FEE`, `DELIVERY_PER_KM`.
5. **Create the tables and your admin, once, from your own computer**, pointing at the hosted database
   (copy the connection string from the Neon dashboard):
   ```
   # PowerShell
   $env:DATABASE_URL = "postgresql://..."
   flask --app wsgi init-db
   flask --app wsgi create-admin
   flask --app wsgi seed-demo        # optional demo shops and products
   ```
   The commands print the database type. It must say `postgresql`, not `sqlite`.
6. **Deploy**, then open `/healthz` (should show `{"status":"ok"}`) and sign in at `/login`. Check `/admin/system`.
7. **Allow your new web address** for the Geoapify key in the Geoapify project settings.

Change the database layout later with Flask-Migrate (`flask db init`, `flask db migrate`, `flask db upgrade`) and run
`flask db upgrade` against the hosted database before each deploy that changes tables.

**Monitoring.** `/admin/users` shows every account and when they last signed in. `/admin/system` shows which APIs are
configured. Vercel's Logs tab shows errors, and `/healthz` can be watched by a free uptime monitor.
