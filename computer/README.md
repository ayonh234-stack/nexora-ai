# Nexora virtual computer (Render free web service)

This folder is a small owner-only API: run Python, open a public page (screenshot + text when Chromium works), and read/write files in a sandbox folder.

It is meant to run on Render's free plan (no credit card). The service sleeps after 15 minutes idle and takes about a minute to wake. Files on disk do not survive sleep, restart, or redeploy.

Secrets (`BOX_TOKEN`) are set as Render environment variables. Do not put tokens in this folder.
