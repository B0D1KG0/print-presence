# Security Policy

## Supported versions

Only the [latest release](https://github.com/B0D1KG0/print-presence/releases/latest) gets fixes.
Please update before reporting.

## What the app stores

- Your printer's IP, serial number and **Access Code** are saved only on your PC in
  `%APPDATA%\PrintPresence\settings.json` (or your own `config.toml`). They are never sent anywhere
  except to your printer on the local network.
- The app talks to: your printer (MQTT over TLS, local network), the Discord desktop app (local IPC),
  `discord.com` / `cdn.discordapp.com` (printer pictures) and `api.github.com` (update check).

## Reporting a vulnerability

Please **don't** open a public issue for security problems.

Use GitHub's private reporting: **Security → Report a vulnerability** on this repository
([direct link](https://github.com/B0D1KG0/print-presence/security/advisories/new)).
You'll get an answer within a few days. Please give a reasonable time to release a fix before disclosing it publicly.
