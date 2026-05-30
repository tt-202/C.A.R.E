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
import { saveCareProfile } from "@/lib/saveCareProfile";

/**
 * High-contrast, warm cream fields — easier to see than light gray on white
 * (common preference for older adults: warm paper tone + dark text + strong borders).
 */
const authInputClass =
  "h-14 rounded-2xl border-2 border-stone-600 bg-[#fffefb] text-lg text-stone-950 placeholder:text-stone-500 focus-visible:border-blue-800 focus-visible:ring-2 focus-visible:ring-blue-900/40";

export type UserRole = "caregiver" | "user";

export type AuthUser = {
  name: string;
  email: string;
  /** Set on the screen after login (caregiver vs user). */
  role?: UserRole;
};

/** Firebase Auth errors expose `code` (e.g. auth/invalid-api-key); message alone often omits it. */
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
    return "App is missing Firebase settings. Add NEXT_PUBLIC_FIREBASE_API_KEY, AUTH_DOMAIN, and PROJECT_ID in .env.local (local) or in Vercel → Settings → Environment Variables, then redeploy.";
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
    return "That email address doesn’t look valid.";
  }
  if (raw.includes("auth/popup-closed-by-user") || raw.includes("auth/cancelled-popup-request")) {
    return "Sign-in was cancelled.";
  }
  if (raw.includes("auth/operation-not-allowed")) {
    return "That sign-in method is turned off in Firebase. In Firebase Console → Authentication → Sign-in method, enable Email/Password and/or Google.";
  }
  if (raw.includes("auth/unauthorized-domain")) {
    return "This site’s domain is not allowed for Firebase Auth. In Firebase Console → Authentication → Settings → Authorized domains, add this host (e.g. your-app.vercel.app and localhost).";
  }
  if (raw.includes("auth/invalid-api-key") || raw.includes("auth/api-key-not-valid")) {
    return "Firebase API key is missing or wrong. Check NEXT_PUBLIC_FIREBASE_* matches your Firebase project.";
  }
  if (raw.includes("auth/network-request-failed")) {
    return "Could not reach Firebase. Check your network and try again.";
  }
  if (raw.includes("auth/too-many-requests")) {
    return "Too many attempts. Wait a few minutes and try again.";
  }
  if (raw.includes("auth/user-disabled")) {
    return "This account has been disabled.";
  }
  return "Something went wrong. Please try again.";
}

type AuthPageProps = {
  /** Called after a successful sign-in so the parent can update immediately (avoids missed auth listener in some Next.js bundles). */
  onSignedIn?: (user: User) => void;
};

export default function AuthPage({ onSignedIn }: AuthPageProps) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [careRecipientName, setCareRecipientName] = useState("");
  const [caregiverName, setCaregiverName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    const trimmedEmail = email.trim();
    const trimmedUserName = careRecipientName.trim();
    const trimmedCaregiverName = caregiverName.trim();

    if (!trimmedUserName) {
      setError("Please enter the user name (person receiving care).");
      return;
    }
    if (!trimmedCaregiverName) {
      setError("Please enter the caregiver name.");
      return;
    }
    if (!trimmedEmail) {
      setError("Please enter your email.");
      return;
    }
    if (!password) {
      setError("Please enter a password.");
      return;
    }
    if (mode === "signup") {
      if (password !== confirmPassword) {
        setError("Passwords do not match. Try again.");
        return;
      }
      if (password.length < 6) {
        setError("Use at least 6 characters for your password.");
        return;
      }
    }

    setBusy(true);
    try {
      const auth = getClientAuth();
      if (mode === "signup") {
        const cred = await createUserWithEmailAndPassword(auth, trimmedEmail, password);
        await updateProfile(cred.user, { displayName: trimmedCaregiverName });
        await saveCareProfile(
          cred.user.uid,
          () => cred.user.getIdToken(),
          trimmedUserName,
          trimmedCaregiverName,
        );
        onSignedIn?.(cred.user);
      } else {
        const cred = await signInWithEmailAndPassword(auth, trimmedEmail, password);
        await saveCareProfile(
          cred.user.uid,
          () => cred.user.getIdToken(),
          trimmedUserName,
          trimmedCaregiverName,
        );
        onSignedIn?.(cred.user);
      }
    } catch (err: unknown) {
      setError(mapFirebaseError(firebaseErrorFingerprint(err)));
    } finally {
      setBusy(false);
    }
  };

  const handleGoogle = async () => {
    setError(null);
    const trimmedUserName = careRecipientName.trim();
    const trimmedCaregiverName = caregiverName.trim();
    if (!trimmedUserName) {
      setError("Please enter the user name (person receiving care).");
      return;
    }
    if (!trimmedCaregiverName) {
      setError("Please enter the caregiver name.");
      return;
    }
    setBusy(true);
    try {
      const auth = getClientAuth();
      const provider = new GoogleAuthProvider();
      const cred = await signInWithPopup(auth, provider);
      await saveCareProfile(
        cred.user.uid,
        () => cred.user.getIdToken(),
        trimmedUserName,
        trimmedCaregiverName,
      );
      onSignedIn?.(cred.user);
    } catch (err: unknown) {
      setError(mapFirebaseError(firebaseErrorFingerprint(err)));
    } finally {
      setBusy(false);
    }
  };

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
            <p className="mb-4 text-center text-xl font-bold text-stone-950">
              {mode === "login" ? "Welcome back" : "Create your account"}
            </p>

            <div className="mb-6 grid grid-cols-2 gap-3">
              <Button
                type="button"
                className={cn(
                  "h-14 rounded-2xl border-2 text-lg font-semibold",
                  mode === "login"
                    ? "border-blue-950 bg-blue-900 text-white shadow-md hover:bg-blue-950"
                    : "border-stone-600 bg-stone-200 text-stone-900 hover:bg-stone-100"
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
                  "h-14 rounded-2xl border-2 text-lg font-semibold",
                  mode === "signup"
                    ? "border-blue-950 bg-blue-900 text-white shadow-md hover:bg-blue-950"
                    : "border-stone-600 bg-stone-200 text-stone-900 hover:bg-stone-100"
                )}
                onClick={() => {
                  setMode("signup");
                  setError(null);
                }}
              >
                Sign up
              </Button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label htmlFor="auth-user-name" className="mb-2 block text-lg font-semibold text-stone-900">
                  User name
                </label>
                <p className="mb-2 text-sm font-medium text-stone-700">
                  Person receiving care (using the User section of the app).
                </p>
                <Input
                  id="auth-user-name"
                  name="careRecipientName"
                  autoComplete="name"
                  value={careRecipientName}
                  onChange={(e) => setCareRecipientName(e.target.value)}
                  placeholder="e.g. Alex Carter"
                  className={authInputClass}
                />
              </div>

              <div>
                <label htmlFor="auth-caregiver-name" className="mb-2 block text-lg font-semibold text-stone-900">
                  Caregiver name
                </label>
                <p className="mb-2 text-sm font-medium text-stone-700">
                  Family or staff helping with meals.
                </p>
                <Input
                  id="auth-caregiver-name"
                  name="caregiverName"
                  autoComplete="name"
                  value={caregiverName}
                  onChange={(e) => setCaregiverName(e.target.value)}
                  placeholder="e.g. Sam Carter"
                  className={authInputClass}
                />
              </div>

              <div>
                <label htmlFor="auth-email" className="mb-2 block text-lg font-semibold text-stone-900">
                  Email
                </label>
                <Input
                  id="auth-email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  inputMode="email"
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
                  name="password"
                  type="password"
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className={authInputClass}
                />
              </div>

              {mode === "signup" && (
                <div>
                  <label htmlFor="auth-confirm" className="mb-2 block text-lg font-semibold text-stone-900">
                    Confirm password
                  </label>
                  <Input
                    id="auth-confirm"
                    name="confirmPassword"
                    type="password"
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className={authInputClass}
                  />
                </div>
              )}

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
                {mode === "login" ? "Log in" : "Create account"}
              </Button>
            </form>

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
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
