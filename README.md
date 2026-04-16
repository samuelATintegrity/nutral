# Nūtral — Landing Page

Marketing site for **nutral.news**. Captures waitlist signups into Supabase.

> **Brand note:** the display name uses a macron (**Nūtral**) but the domain stays `nutral.news` — domains can't have a macron.

Single static HTML file. No build step. No frameworks.

## Files

- `index.html` — the landing page (HTML + CSS + JS, all in one file)
- `README.md` — this file

## Local preview

Just open `index.html` in a browser. Forms will fall back to "dev mode" (console log + success state) if Supabase keys aren't configured.

```
start index.html
```

## Supabase setup (5 min)

1. Create a new project at [supabase.com](https://supabase.com).
2. In the SQL editor, run:

   ```sql
   create table waitlist (
     id uuid primary key default gen_random_uuid(),
     email text not null unique,
     topics text[] default array[]::text[],
     created_at timestamptz default now()
   );

   alter table waitlist enable row level security;

   create policy "Anyone can join the waitlist"
     on waitlist for insert
     to anon
     with check (true);
   ```

3. Go to **Project Settings → API** and copy:
   - **Project URL** (e.g. `https://xxxxxxxx.supabase.co`)
   - **anon public** key (the `eyJhbGciOi...` starting one — safe to use in the browser)

4. Open `index.html` and paste them into the two constants near the bottom:

   ```js
   const SUPABASE_URL = "https://xxxxxxxx.supabase.co";
   const SUPABASE_ANON_KEY = "eyJhbGciOi...";
   ```

5. Refresh the page. Submit your email. Check the `waitlist` table — you should see the row.

## Deploy to Vercel

1. Push this folder to a GitHub repo (e.g. `nutral-landing`).
2. At [vercel.com](https://vercel.com/new), import the repo. No framework preset needed — Vercel will serve `index.html` as static.
3. Deploy. You'll get a `*.vercel.app` URL.

## Custom domain (nutral.news)

1. In Vercel → **Settings → Domains**, add `nutral.news` and `www.nutral.news`.
2. Vercel will show you DNS records to add.
3. In Namecheap → **Domain List → Manage → Advanced DNS**:
   - Delete the default parking records.
   - Add an **A record** for `@` pointing to Vercel's IP (`76.76.21.21` at time of writing — use whatever Vercel gives you).
   - Add a **CNAME record** for `www` pointing to `cname.vercel-dns.com`.
4. Wait 5–60 min for DNS to propagate. Vercel will auto-issue an SSL cert.

## Editing the page

Everything is in `index.html`:

- **Copy**: search for the section comments (`<!-- ============== HERO ============== -->`).
- **Colors**: edit the CSS variables at the top of `<style>` (`:root { ... }`).
- **Headline options**: there's a comment above the `<h1>` with swappable alternates.
- **Fonts**: Google Fonts link in `<head>` — change `Fraunces` or `Inter` there.

## Known TODOs

- [ ] Replace placeholder links in the footer (Privacy, Terms, Contact)
- [ ] Add real testimonials to the Social Proof section when they exist
- [ ] Add analytics (Plausible or Vercel Analytics) once traffic starts
- [ ] Consider adding a topic preference step on signup (extend `waitlist.topics` array)
