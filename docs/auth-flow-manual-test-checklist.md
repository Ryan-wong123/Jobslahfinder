# Auth Flow Manual Test Checklist

Run this checklist against a local environment after backend migrations are applied and the frontend is reachable through the reverse proxy.

## Setup

- [ ] Start the stack with `docker compose up --build`.
- [ ] Apply migrations with `docker compose run --rm backend alembic upgrade head`.
- [ ] Open `http://localhost:8080`.
- [ ] Use a test email and a password that is at least 12 characters and includes uppercase, lowercase, and a number.

## Registration and Login

- [ ] Register a new account from `/register`.
- [ ] Confirm the app redirects to `/login?registered=1`.
- [ ] Confirm the login page shows a safe success message after registration.
- [ ] Attempt login with a wrong password and confirm the UI shows only `Invalid email or password.`.
- [ ] Log in with the correct password and confirm the app opens `/account`.
- [ ] Confirm no session token is stored in browser localStorage or sessionStorage.

## Account and Profile

- [ ] Open `/account` while logged in.
- [ ] Update profile fields and confirm the page shows `Profile updated.`.
- [ ] Try an invalid profile value and confirm the UI shows a safe generic error.
- [ ] Change the password with the current password and a strong new password.
- [ ] Sign out and confirm protected pages redirect to `/login`.
- [ ] Sign in with the new password and confirm the old password no longer works.

## Password Reset

- [ ] Open `/forgot-password`.
- [ ] Submit a known email and confirm the same generic reset message is shown.
- [ ] Submit an unknown email and confirm the same generic reset message is shown.
- [ ] Open `/reset-password`.
- [ ] Submit an invalid token and confirm the UI shows only `Unable to reset password.`.
- [ ] Complete a valid reset token flow if a test token is available from the backend test environment.

## Account Deletion

- [ ] Open `/account`.
- [ ] Start account deletion and cancel it.
- [ ] Start account deletion again and submit the wrong password.
- [ ] Confirm the account remains active after the wrong password.
- [ ] Submit the correct password and confirm the user is redirected to `/login`.
- [ ] Confirm the deleted account can no longer log in.
