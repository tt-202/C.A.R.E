"use client";

import { useState, type FormEvent } from "react";
import { HeartPulse } from "lucide-react";
import {
  createUserWithEmailAndPassword,
  GoogleAuthProvider,
  signInWithEmailAndPassword,
  signInWithPopup,
  updateProfile,
  type User,
} from "firebase/auth";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { getClientAuth } from "@/lib/firebaseClient";
import type { CareProfile } from "@/lib/careProfileStorage";
import {
  acceptInviteCode,
  loadProfileFromServer,
  saveCareProfile,
} from "@/lib/saveCareProfile";

const authInputClass =
  "h-14 rounded-2xl border-2 border-stone-600 bg-[#fffefb] text-lg text-stone-950 placeholder:text-stone-500 focus-visible:border-blue-800 focus-visible:ring-2 focus-visible:ring-blue-900/40";

export type UserRole = "caregiver" | "user";

function firebaseErrorFingerprint(err: unknown): string {
  if (typeof err === "object" && err !== null && "code" in err) {
    const code = String((err as { code: string }).code);
    const message = "message" in err ? String((err as { message?: string }).message ?? "") : "";
    return `${code} ${message}`;
  }
  return err instanceof Error ? err.message : String(err);
}

function mapFirebaseError(raw: string): string {
  if (raw.includes("Firebase client is not configured") || raw.includes("NEXT_PUBLIC_FIREBASE")) {
    return "App is missing Firebase settings. Add NEXT_PUBLIC_FIREBASE_* in .env.local or Vercel env vars.";
  }
  if (
    raw.includes("auth/invalid-credential") ||
    raw.includes("auth/wrong-password") ||
    raw.includes("auth/user-not-found")
  ) {
    return "Email or password is not correct. Try again.";
  }
  if (raw.includes("auth/email-already-in-use")) {
    return "That email already has an account. Try logging in.";
  }
  if (raw.includes("auth/weak-password")) {
    return "Use a stronger password (at least 6 characters).";
  }
  if (raw.includes("auth/invalid-email")) {
    return "That email address doesn't look valid.";
  }
  if (raw.includes("auth/popup-closed-by-user") || raw.includes("auth/cancelled-popup-request")) {
    return "Sign-in was cancelled.";
  }
  return "Something went wrong. Please try again.";
}

type AuthPageProps = {
  initialMode?: "auth" | "setup";
  existingUser?: User;
  onSignedIn?: (user: User, profile?: CareProfile) => void;
  onSignOut?: () => void;
};

export default function AuthPage({
  initialMode = "auth",
  existingUser,
  onSignedIn,
  onSignOut,
}: AuthPageProps) {
  const [flow, setFlow] = useState<"caregiver" | "join">("caregiver");
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [careRecipientName, setCareRecipientName] = useState("");
  const [caregiverName, setCaregiverName] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [email, setEmail] = useState(existingUser?.email ?? "");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const finishAuth = async (cred: User, profile?: CareProfile | null) => {
    if (profile) {
      onSignedIn?.(cred, profile);
      return;
    }
    const loaded = await loadProfileFromServer(cred.uid, () => cred.getIdToken());
    onSignedIn?.(cred, loaded ?? undefined);
  };

  const handleJoinAfterAuth = async (cred: User) => {
    const code = inviteCode.trim().toUpperCase();
    if (!code) {
      setError("Enter the invite code from your caregiver.");
      return false;
    }
    const accepted = await acceptInviteCode(() => cred.getIdToken(), code, cred.uid);
    if (!accepted.ok) {
      setError(accepted.error);
      return false;
    }
    onSignedIn?.(cred, accepted.profile);
    return true;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    const trimmedEmail = email.trim();
    if (!trimmedEmail || !password) {
      setError("Email and password are required.");
      return;
    }
    if (mode === "signup" && password !== confirmPassword) {
      setError("Passwords do not match. Try again.");
      return;
    }
    if (mode === "signup" && password.length < 6) {
      setError("Use at least 6 characters for your password.");
      return;
    }

    if (flow === "caregiver") {
      const trimmedUserName = careRecipientName.trim();
      const trimmedCaregiverName = caregiverName.trim();
      if (!trimmedUserName || !trimmedCaregiverName) {
        setError("Enter both the user name and caregiver name.");
        return;
      }
    } else if (!inviteCode.trim()) {
      setError("Enter the invite code from your caregiver.");
      return;
    }

    setBusy(true);
    try {
      if (existingUser && initialMode === "setup") {
        if (flow === "join") {
          await handleJoinAfterAuth(existingUser);
        } else {
          const profile = await saveCareProfile(
            existingUser.uid,
            () => existingUser.getIdToken(),
            "caregiver",
            careRecipientName.trim(),
            caregiverName.trim(),
          );
          if (!profile) {
            setError("Could not create your care pair. Try again.");
            return;
          }
          onSignedIn?.(existingUser, profile);
        }
        return;
      }

      const auth = getClientAuth();
      let cred: User;
      if (mode === "signup") {
        cred = (await createUserWithEmailAndPassword(auth, trimmedEmail, password)).user;
        if (flow === "caregiver") {
          await updateProfile(cred, { displayName: caregiverName.trim() });
        }
      } else {
        cred = (await signInWithEmailAndPassword(auth, trimmedEmail, password)).user;
      }

      if (flow === "join") {
        const ok = await handleJoinAfterAuth(cred);
        if (!ok) return;
      } else if (mode === "signup") {
        const profile = await saveCareProfile(
          cred.uid,
          () => cred.getIdToken(),
          "caregiver",
          careRecipientName.trim(),
          caregiverName.trim(),
        );
        if (!profile) {
          setError("Could not create your care pair. Try again.");
          return;
        }
        onSignedIn?.(cred, profile);
      } else {
        await finishAuth(cred);
      }
    } catch (err: unknown) {
      setError(mapFirebaseError(firebaseErrorFingerprint(err)));
    } finally {
      setBusy(false);
    }
  };

  const handleGoogle = async () => {
    setError(null);
    if (flow === "caregiver") {
      if (!careRecipientName.trim() || !caregiverName.trim()) {
        setError("Enter both names before continuing with Google.");
        return;
      }
    } else if (!inviteCode.trim()) {
      setError("Enter the invite code before continuing with Google.");
      return;
    }

    setBusy(true);
    try {
      const auth = getClientAuth();
      const provider = new GoogleAuthProvider();
      const cred = await signInWithPopup(auth, provider);

      if (flow === "join") {
        const ok = await handleJoinAfterAuth(cred.user);
        if (!ok) return;
      } else {
        const profile = await saveCareProfile(
          cred.user.uid,
          () => cred.user.getIdToken(),
          "caregiver",
          careRecipientName.trim(),
          caregiverName.trim(),
        );
        if (!profile) {
          setError("Could not create your care pair. Try again.");
          return;
        }
        onSignedIn?.(cred.user, profile);
      }
    } catch (err: unknown) {
      setError(mapFirebaseError(firebaseErrorFingerprint(err)));
    } finally {
      setBusy(false);
    }
  };

  const showNames = flow === "caregiver";
  const title =
    initialMode === "setup"
      ? "Finish setting up C.A.R.E"
      : mode === "login"
        ? "Welcome back"
        : "Create your account";

  return (
    <div className="min-h-screen p-4 pb-12 md:flex md:items-center md:justify-center md:p-8">
      <div className="mx-auto w-full max-w-md">
        <header className="mb-8 text-center">
          <div className="mb-4 flex justify-center">
            <div className="rounded-3xl border-2 border-stone-700 bg-[#f5ebe0] p-4 text-blue-900 shadow-lg">
              <HeartPulse className="h-14 w-14 md:h-16 md:w-16" strokeWidth={2} aria-hidden />
            </div>
          </div>
          <h1 className="text-4xl font-bold tracking-tight text-white md:text-5xl">C.A.R.E</h1>
          <p className="mt-2 text-lg text-amber-100 md:text-xl">Your Helper - Your Friend</p>
        </header>

        <Card className="rounded-3xl border-2 border-stone-700 bg-[#f5ebe0] text-stone-950 shadow-xl ring-0">
          <CardContent className="p-6 md:p-8">
            <p className="mb-4 text-center text-xl font-bold text-stone-950">{title}</p>

            <div className="mb-6 grid grid-cols-2 gap-3">
              <Button
                type="button"
                className={cn(
                  "h-14 rounded-2xl border-2 text-base font-semibold md:text-lg",
                  flow === "caregiver"
                    ? "border-blue-950 bg-blue-900 text-white shadow-md hover:bg-blue-950"
                    : "border-stone-600 bg-stone-200 text-stone-900 hover:bg-stone-100",
                )}
                onClick={() => {
                  setFlow("caregiver");
                  setError(null);
                }}
              >
                I'm the caregiver
              </Button>
              <Button
                type="button"
                className={cn(
                  "h-14 rounded-2xl border-2 text-base font-semibold md:text-lg",
                  flow === "join"
                    ? "border-blue-950 bg-blue-900 text-white shadow-md hover:bg-blue-950"
                    : "border-stone-600 bg-stone-200 text-stone-900 hover:bg-stone-100",
                )}
                onClick={() => {
                  setFlow("join");
                  setError(null);
                }}
              >
                Join with invite
              </Button>
            </div>

            {!existingUser ? (
              <div className="mb-6 grid grid-cols-2 gap-3">
                <Button
                  type="button"
                  className={cn(
                    "h-12 rounded-2xl border-2 text-base font-semibold",
                    mode === "login"
                      ? "border-stone-700 bg-stone-800 text-white"
                      : "border-stone-500 bg-stone-100 text-stone-900",
                  )}
                  onClick={() => {
                    setMode("login");
                    setError(null);
                  }}
                >
                  Log in
                </Button>
                <Button
                  type="button"
                  className={cn(
                    "h-12 rounded-2xl border-2 text-base font-semibold",
                    mode === "signup"
                      ? "border-stone-700 bg-stone-800 text-white"
                      : "border-stone-500 bg-stone-100 text-stone-900",
                  )}
                  onClick={() => {
                    setMode("signup");
                    setError(null);
                  }}
                >
                  Sign up
                </Button>
              </div>
            ) : null}

            <form onSubmit={handleSubmit} className="space-y-5">
              {flow === "join" ? (
                <div>
                  <label htmlFor="auth-invite" className="mb-2 block text-lg font-semibold text-stone-900">
                    Invite code
                  </label>
                  <p className="mb-2 text-sm font-medium text-stone-700">
                    Ask your caregiver for the code — you'll use your own email to sign in.
                  </p>
                  <Input
                    id="auth-invite"
                    name="inviteCode"
                    value={inviteCode}
                    onChange={(e) => setInviteCode(e.target.value.toUpperCase())}
                    placeholder="e.g. A1B2C3D4"
                    className={cn(authInputClass, "uppercase tracking-widest")}
                  />
                </div>
              ) : null}

              {showNames ? (
                <>
                  <div>
                    <label htmlFor="auth-user-name" className="mb-2 block text-lg font-semibold text-stone-900">
                      User name
                    </label>
                    <Input
                      id="auth-user-name"
                      value={careRecipientName}
                      onChange={(e) => setCareRecipientName(e.target.value)}
                      placeholder="Person receiving care"
                      className={authInputClass}
                    />
                  </div>
                  <div>
                    <label htmlFor="auth-caregiver-name" className="mb-2 block text-lg font-semibold text-stone-900">
                      Your name (caregiver)
                    </label>
                    <Input
                      id="auth-caregiver-name"
                      value={caregiverName}
                      onChange={(e) => setCaregiverName(e.target.value)}
                      placeholder="Your name"
                      className={authInputClass}
                    />
                  </div>
                </>
              ) : null}

              {!existingUser ? (
                <>
                  <div>
                    <label htmlFor="auth-email" className="mb-2 block text-lg font-semibold text-stone-900">
                      Email
                    </label>
                    <Input
                      id="auth-email"
                      type="email"
                      autoComplete="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@example.com"
                      className={authInputClass}
                    />
                  </div>
                  <div>
                    <label htmlFor="auth-password" className="mb-2 block text-lg font-semibold text-stone-900">
                      Password
                    </label>
                    <Input
                      id="auth-password"
                      type="password"
                      autoComplete={mode === "login" ? "current-password" : "new-password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className={authInputClass}
                    />
                  </div>
                  {mode === "signup" ? (
                    <div>
                      <label htmlFor="auth-confirm" className="mb-2 block text-lg font-semibold text-stone-900">
                        Confirm password
                      </label>
                      <Input
                        id="auth-confirm"
                        type="password"
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        className={authInputClass}
                      />
                    </div>
                  ) : null}
                </>
              ) : null}

              {error ? (
                <p
                  className="rounded-2xl border-2 border-red-700 bg-red-100 px-4 py-3 text-center text-lg font-medium text-red-950"
                  role="alert"
                >
                  {error}
                </p>
              ) : null}

              <Button
                type="submit"
                disabled={busy}
                className="h-16 w-full rounded-2xl border-2 border-blue-950 bg-blue-900 text-xl font-semibold text-white shadow-md hover:bg-blue-950 disabled:opacity-60"
              >
                {flow === "join"
                  ? existingUser
                    ? "Join care pair"
                    : mode === "login"
                      ? "Log in and join"
                      : "Sign up and join"
                  : existingUser
                    ? "Create care pair"
                    : mode === "login"
                      ? "Log in"
                      : "Create account"}
              </Button>
            </form>

            {!existingUser ? (
              <div className="mt-6">
                <p className="mb-3 text-center text-base font-semibold text-stone-700">Or continue with</p>
                <Button
                  type="button"
                  variant="outline"
                  disabled={busy}
                  className="h-14 w-full rounded-2xl border-2 border-stone-600 bg-[#fffefb] text-lg font-semibold text-stone-900 hover:bg-stone-50 disabled:opacity-60"
                  onClick={handleGoogle}
                >
                  Google
                </Button>
              </div>
            ) : null}

            {existingUser && onSignOut ? (
              <p className="mt-6 text-center">
                <button
                  type="button"
                  className="text-lg font-medium text-stone-700 underline underline-offset-4"
                  onClick={onSignOut}
                >
                  Sign out
                </button>
              </p>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
