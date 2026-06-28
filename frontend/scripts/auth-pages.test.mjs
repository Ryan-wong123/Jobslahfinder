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
  assert.match(resetPasswordPage, /<PasswordResetConfirmForm \/>/);
  assert.match(resetPasswordPage, /href="\/login"/);
});

test("auth forms call the expected backend endpoints with safe generic errors", () => {
  const loginForm = readProjectFile("src", "components", "LoginForm.tsx");
  const registerForm = readProjectFile("src", "components", "RegisterForm.tsx");
  const resetRequestForm = readProjectFile("src", "components", "PasswordResetRequestForm.tsx");
  const resetConfirmForm = readProjectFile("src", "components", "PasswordResetConfirmForm.tsx");

  assert.match(loginForm, /apiFetch<\{ message: string \}>\("\/auth\/login"/);
  assert.match(loginForm, /Invalid email or password\./);
  assert.match(registerForm, /apiFetch<User>\("\/auth\/register"/);
  assert.match(registerForm, /Unable to register account\./);
  assert.match(resetRequestForm, /apiFetch<\{ message: string \}>\("\/auth\/password-reset\/request"/);
  assert.match(resetRequestForm, /Unable to request password reset\./);
  assert.match(resetConfirmForm, /apiFetch<\{ message: string \}>\("\/auth\/password-reset\/confirm"/);
  assert.match(resetConfirmForm, /Unable to reset password\./);
});

test("auth forms avoid browser token storage and include password autocomplete hints", () => {
  const authFiles = [
    readProjectFile("src", "components", "LoginForm.tsx"),
    readProjectFile("src", "components", "RegisterForm.tsx"),
    readProjectFile("src", "components", "PasswordResetRequestForm.tsx"),
    readProjectFile("src", "components", "PasswordResetConfirmForm.tsx"),
    readProjectFile("src", "components", "AccountPanel.tsx")
  ].join("\n");

  assert.doesNotMatch(authFiles, /localStorage|sessionStorage/);
  assert.match(authFiles, /autoComplete="current-password"/);
  assert.match(authFiles, /autoComplete="new-password"/);
  assert.match(authFiles, /autoComplete="one-time-code"/);
});

test("account page contains logout, password change, and re-authenticated deletion flows", () => {
  const accountPanel = readProjectFile("src", "components", "AccountPanel.tsx");

  assert.match(accountPanel, /apiFetch<\{ message: string \}>\("\/auth\/logout"/);
  assert.match(accountPanel, /apiFetch<\{ message: string \}>\("\/auth\/password-change"/);
  assert.match(accountPanel, /apiFetch<\{ message: string \}>\("\/me", \{/);
  assert.match(accountPanel, /password: formData\.get\("password"\)/);
  assert.match(accountPanel, /Unable to delete account\./);
});
