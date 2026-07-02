import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { test } from "node:test";

const root = fileURLToPath(new URL("..", import.meta.url));

function readProjectFile(...segments) {
  return readFileSync(join(root, ...segments), "utf8");
}

test("auth routes render the expected auth forms and navigation links", () => {
  const loginPage = readProjectFile("src", "app", "login", "page.tsx");
  const registerPage = readProjectFile("src", "app", "register", "page.tsx");
  const forgotPasswordPage = readProjectFile("src", "app", "forgot-password", "page.tsx");
  const resetPasswordPage = readProjectFile("src", "app", "reset-password", "page.tsx");

  assert.match(loginPage, /<LoginForm \/>/);
  assert.match(loginPage, /href="\/forgot-password"/);
  assert.match(loginPage, /href="\/register"/);
  assert.match(registerPage, /<RegisterForm \/>/);
  assert.match(registerPage, /href="\/login"/);
  assert.match(forgotPasswordPage, /<PasswordResetRequestForm \/>/);
  assert.match(forgotPasswordPage, /href="\/reset-password"/);
  assert.match(resetPasswordPage, /<PasswordResetConfirmForm(?:\s+[^>]*)?\/>/);
  assert.match(resetPasswordPage, /href="\/login"/);
});

test("auth forms call the expected backend endpoints with safe generic errors", () => {
  const loginForm = readProjectFile("src", "components", "LoginForm.tsx");
  const registerForm = readProjectFile("src", "components", "RegisterForm.tsx");
  const resetRequestForm = readProjectFile("src", "components", "PasswordResetRequestForm.tsx");
  const resetConfirmForm = readProjectFile("src", "components", "PasswordResetConfirmForm.tsx");

  assert.match(loginForm, /apiFetch<LoginResponse>\("\/auth\/login"/);  
  assert.match(loginForm, /Invalid email or password\./);
  assert.match(registerForm, /apiFetch<User>\("\/auth\/register"/);
  assert.match(registerForm, /Unable to register account\./);
  assert.match(resetRequestForm, /apiFetch<\{ message: string \}>\("\/auth\/password-reset\/request"/);
  assert.match(resetRequestForm, /Unable to request password reset\./);
  assert.match(resetConfirmForm, /apiFetch<\{ message: string \}>\("\/auth\/password-reset\/confirm"/);
  assert.match(resetConfirmForm, /Unable to reset password\./);
});

test("login flow routes users into required two-factor flows", () => {
  const loginForm = readProjectFile("src", "components", "LoginForm.tsx");

  assert.match(loginForm, /result\.requires_2fa && result\.challenge_token/);
  assert.match(loginForm, /router\.push\(`\/two-factor\/verify\?challenge=\$\{encodeURIComponent\(result\.challenge_token\)\}`\)/);
  assert.match(loginForm, /result\.requires_2fa_setup/);
  assert.match(loginForm, /router\.push\("\/two-factor\/setup"\)/);
});

test("two-factor forms call expected endpoints without browser token storage", () => {
  const setupPanel = readProjectFile("src", "components", "TwoFactorSetupPanel.tsx");
  const verifyPanel = readProjectFile("src", "components", "TwoFactorVerifyPanel.tsx");
  const twoFactorFiles = `${setupPanel}\n${verifyPanel}`;

  assert.match(setupPanel, /apiFetch<TwoFactorSetup>\("\/auth\/2fa\/setup"\)/);
  assert.match(setupPanel, /apiFetch<\{ message: string \}>\("\/auth\/2fa\/confirm"/);
  assert.match(setupPanel, /QRCode\.toDataURL\(currentSetup\.provisioning_uri/);
  assert.match(setupPanel, /autoComplete="one-time-code"/);
  assert.match(setupPanel, /router\.push\("\/account"\)/);

  assert.match(verifyPanel, /searchParams\.get\("challenge"\)/);
  assert.match(verifyPanel, /apiFetch<\{ message: string \}>\("\/auth\/2fa\/verify"/);
  assert.match(verifyPanel, /challenge_token: challenge/);
  assert.match(verifyPanel, /Missing verification challenge\. Sign in again\./);
  assert.match(verifyPanel, /autoComplete="one-time-code"/);
  assert.match(verifyPanel, /router\.push\("\/account"\)/);

  assert.doesNotMatch(twoFactorFiles, /localStorage|sessionStorage/);
});

test("auth forms avoid browser token storage and include password autocomplete hints", () => {
  const authFiles = [
    readProjectFile("src", "components", "LoginForm.tsx"),
    readProjectFile("src", "components", "RegisterForm.tsx"),
    readProjectFile("src", "components", "PasswordResetRequestForm.tsx"),
    readProjectFile("src", "components", "PasswordResetConfirmForm.tsx"),
    readProjectFile("src", "components", "AccountPanel.tsx"),
    readProjectFile("src", "components", "TwoFactorSetupPanel.tsx"),
    readProjectFile("src", "components", "TwoFactorVerifyPanel.tsx")
  ].join("\n");

  assert.doesNotMatch(authFiles, /localStorage|sessionStorage/);
  assert.match(authFiles, /autoComplete="current-password"/);
  assert.match(authFiles, /autoComplete="new-password"/);
  assert.match(authFiles, /autoComplete="one-time-code"/);
});

test("auth forms include client-side validation matching backend boundaries", () => {
  const loginForm = readProjectFile("src", "components", "LoginForm.tsx");
  const registerForm = readProjectFile("src", "components", "RegisterForm.tsx");
  const resetRequestForm = readProjectFile("src", "components", "PasswordResetRequestForm.tsx");
  const resetConfirmForm = readProjectFile("src", "components", "PasswordResetConfirmForm.tsx");

  assert.match(registerForm, /maxLength=\{255\}/);
  assert.match(registerForm, /maxLength=\{128\}/);
  assert.match(registerForm, /Password must be 12-128 characters/);
  assert.match(loginForm, /password\.length < 1 \|\| password\.length > 128/);
  assert.match(resetRequestForm, /Enter a valid email address\./);
  assert.match(resetConfirmForm, /\[A-Za-z0-9_-\]\{43\}/);
  assert.match(resetConfirmForm, /Reset token format is invalid/);
});

test("account page contains logout, password change, and re-authenticated deletion flows", () => {
  const accountPanel = readProjectFile("src", "components", "AccountPanel.tsx");

  assert.match(accountPanel, /apiFetch<\{ message: string \}>\("\/auth\/logout"/);
  assert.match(accountPanel, /apiFetch<\{ message: string \}>\("\/auth\/password-change"/);
  assert.match(accountPanel, /apiFetch<\{ message: string \}>\("\/me", \{/);
  assert.match(accountPanel, /password: formData\.get\("password"\)/);
  assert.match(accountPanel, /Unable to delete account\./);
});
