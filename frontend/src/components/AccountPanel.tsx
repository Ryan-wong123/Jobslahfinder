"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, formatDateTime, type Profile, type User } from "@/lib/api";
import { FormMessage, SubmitButton, TextField } from "./FormControls";

type ProfileForm = {
  full_name: string;
  phone: string;
  location: string;
  summary: string;
  skills: string;
};

const emptyProfileForm: ProfileForm = {
  full_name: "",
  phone: "",
  location: "",
  summary: "",
  skills: ""
};

function profileToForm(profile: Profile | null): ProfileForm {
  if (!profile) {
    return emptyProfileForm;
  }
  return {
    full_name: profile.full_name ?? "",
    phone: profile.phone ?? "",
    location: profile.location ?? "",
    summary: profile.summary ?? "",
    skills: profile.skills.join(", ")
  };
}

export function AccountPanel() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [profileForm, setProfileForm] = useState<ProfileForm>(emptyProfileForm);
  const [loading, setLoading] = useState(true);
  const [pendingProfile, setPendingProfile] = useState(false);
  const [pendingPassword, setPendingPassword] = useState(false);
  const [pendingLogout, setPendingLogout] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [accountError, setAccountError] = useState<string | null>(null);
  const [profileMessage, setProfileMessage] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([apiFetch<User>("/me"), apiFetch<Profile>("/me/profile")])
      .then(([currentUser, currentProfile]) => {
        if (active) {
          setUser(currentUser);
          setProfile(currentProfile);
          setProfileForm(profileToForm(currentProfile));
        }
      })
      .catch(() => {
        router.replace("/login");
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [router]);

  function updateProfileField(field: keyof ProfileForm, value: string) {
    setProfileForm((current) => ({ ...current, [field]: value }));
  }

  async function onProfileUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPendingProfile(true);
    setProfileMessage(null);
    setProfileError(null);

    const skills = profileForm.skills
      .split(",")
      .map((skill) => skill.trim())
      .filter(Boolean);

    try {
      const updatedProfile = await apiFetch<Profile>("/me/profile", {
        method: "PATCH",
        body: JSON.stringify({
          full_name: profileForm.full_name,
          phone: profileForm.phone,
          location: profileForm.location,
          summary: profileForm.summary,
          skills
        })
      });
      setProfile(updatedProfile);
      setProfileForm(profileToForm(updatedProfile));
      setProfileMessage("Profile updated.");
    } catch (caught) {
      setProfileError(caught instanceof Error ? caught.message : "Unable to update profile.");
    } finally {
      setPendingProfile(false);
    }
  }

  async function onPasswordChange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setPendingPassword(true);
    setPasswordMessage(null);
    setPasswordError(null);

    const formData = new FormData(form);
    try {
      const response = await apiFetch<{ message: string }>("/auth/password-change", {
        method: "POST",
        body: JSON.stringify({
          current_password: formData.get("current_password"),
          new_password: formData.get("new_password")
        })
      });
      setPasswordMessage(response.message);
      form.reset();
    } catch (caught) {
      setPasswordError(caught instanceof Error ? caught.message : "Unable to change password.");
    } finally {
      setPendingPassword(false);
    }
  }

  async function onLogout() {
    setPendingLogout(true);
    setAccountError(null);
    try {
      await apiFetch<{ message: string }>("/auth/logout", { method: "POST" });
      router.push("/login");
      router.refresh();
    } catch (caught) {
      setAccountError(caught instanceof Error ? caught.message : "Unable to log out.");
      setPendingLogout(false);
    }
  }

  async function onDeleteAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPendingDelete(true);
    setDeleteError(null);

    const formData = new FormData(event.currentTarget);
    try {
      await apiFetch<{ message: string }>("/me", {
        method: "DELETE",
        body: JSON.stringify({
          password: formData.get("password")
        })
      });
      router.push("/login");
      router.refresh();
    } catch (caught) {
      setDeleteError(caught instanceof Error ? caught.message : "Unable to delete account.");
      setPendingDelete(false);
    }
  }

  if (loading) {
    return <p className="text-sm text-zinc-600">Loading account...</p>;
  }

  if (!user) {
    return null;
  }

  return (
    <div className="space-y-6">
      <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
        <form onSubmit={onProfileUpdate}>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold text-zinc-950">Account Profile</h1>
              <p className="mt-1 text-sm text-zinc-600">{user.email}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded border border-teal-200 bg-teal-50 px-3 py-1 text-xs font-medium text-teal-800">
                {user.role}
              </span>
              <span className="rounded border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs font-medium text-zinc-700">
                {user.is_active ? "Active" : "Inactive"}
              </span>
            </div>
          </div>

          <FormMessage message={accountError} tone="error" />
          <FormMessage message={profileMessage} tone="success" />
          <FormMessage message={profileError} tone="error" />

          <dl className="mt-6 grid gap-4 border-y border-zinc-200 py-5 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <dt className="text-xs font-medium uppercase text-zinc-500">Last login</dt>
              <dd className="mt-1 text-sm text-zinc-950">{formatDateTime(user.last_login_at)}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium uppercase text-zinc-500">Created</dt>
              <dd className="mt-1 text-sm text-zinc-950">{formatDateTime(user.created_at)}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium uppercase text-zinc-500">Profile updated</dt>
              <dd className="mt-1 text-sm text-zinc-950">{formatDateTime(profile?.updated_at ?? null)}</dd>
            </div>
          </dl>

          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="text-sm font-medium text-zinc-800">Full name</span>
              <input
                className="mt-2 w-full rounded border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 outline-none transition focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
                maxLength={255}
                name="full_name"
                onChange={(event) => updateProfileField("full_name", event.target.value)}
                type="text"
                value={profileForm.full_name}
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-zinc-800">Phone</span>
              <input
                className="mt-2 w-full rounded border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 outline-none transition focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
                maxLength={50}
                name="phone"
                onChange={(event) => updateProfileField("phone", event.target.value)}
                type="tel"
                value={profileForm.phone}
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-zinc-800">Location</span>
              <input
                className="mt-2 w-full rounded border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 outline-none transition focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
                maxLength={255}
                name="location"
                onChange={(event) => updateProfileField("location", event.target.value)}
                type="text"
                value={profileForm.location}
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-zinc-800">Skills</span>
              <input
                className="mt-2 w-full rounded border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 outline-none transition focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
                maxLength={800}
                name="skills"
                onChange={(event) => updateProfileField("skills", event.target.value)}
                type="text"
                value={profileForm.skills}
              />
            </label>
            <label className="block md:col-span-2">
              <span className="text-sm font-medium text-zinc-800">Summary</span>
              <textarea
                className="mt-2 min-h-28 w-full resize-y rounded border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 outline-none transition focus:border-teal-700 focus:ring-2 focus:ring-teal-100"
                maxLength={2000}
                name="summary"
                onChange={(event) => updateProfileField("summary", event.target.value)}
                value={profileForm.summary}
              />
            </label>
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <button
              className="rounded bg-zinc-950 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-400"
              disabled={pendingProfile}
              type="submit"
            >
              {pendingProfile ? "Saving..." : "Save profile"}
            </button>
            <button
              className="rounded border border-zinc-300 bg-white px-4 py-2.5 text-sm font-medium text-zinc-900 transition hover:bg-zinc-100 disabled:cursor-not-allowed disabled:text-zinc-400"
              disabled={pendingLogout}
              onClick={onLogout}
              type="button"
            >
              {pendingLogout ? "Signing out..." : "Sign out"}
            </button>
            {user.role === "ADMIN" ? (
              <a
                className="rounded border border-zinc-300 bg-white px-4 py-2.5 text-sm font-medium text-zinc-900 transition hover:bg-zinc-100"
                href="/admin"
              >
                Admin tools
              </a>
            ) : null}
          </div>
        </form>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded border border-zinc-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-zinc-950">Password</h2>
          <form className="mt-5 space-y-4" onSubmit={onPasswordChange}>
            <FormMessage message={passwordMessage} tone="success" />
            <FormMessage message={passwordError} tone="error" />
            <TextField
              label="Current password"
              name="current_password"
              type="password"
              autoComplete="current-password"
            />
            <TextField
              label="New password"
              name="new_password"
              type="password"
              autoComplete="new-password"
              minLength={12}
            />
            <SubmitButton pending={pendingPassword}>Change password</SubmitButton>
          </form>
        </section>

        <section className="rounded border border-red-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-zinc-950">Delete Account</h2>
          <p className="mt-2 text-sm text-zinc-600">
            This disables your account, clears profile details, and signs out active sessions.
          </p>
          {!deleteOpen ? (
            <button
              className="mt-5 rounded border border-red-300 bg-white px-4 py-2 text-sm font-medium text-red-700 transition hover:bg-red-50"
              onClick={() => {
                setDeleteOpen(true);
                setDeleteError(null);
              }}
              type="button"
            >
              Delete account
            </button>
          ) : (
            <form className="mt-5 space-y-4" onSubmit={onDeleteAccount}>
              <FormMessage message={deleteError} tone="error" />
              <TextField
                label="Confirm password"
                name="password"
                type="password"
                autoComplete="current-password"
              />
              <div className="flex flex-wrap gap-3">
                <button
                  className="rounded border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-900 transition hover:bg-zinc-100 disabled:cursor-not-allowed disabled:text-zinc-400"
                  disabled={pendingDelete}
                  onClick={() => setDeleteOpen(false)}
                  type="button"
                >
                  Cancel
                </button>
                <button
                  className="rounded bg-red-700 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-800 disabled:cursor-not-allowed disabled:bg-red-300"
                  disabled={pendingDelete}
                  type="submit"
                >
                  {pendingDelete ? "Deleting..." : "Confirm delete"}
                </button>
              </div>
            </form>
          )}
        </section>
      </div>
    </div>
  );
}
