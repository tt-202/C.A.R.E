"use client";

import { useState, type FormEvent } from "react";
import { HeartPulse } from "lucide-react";
import {
  createUserWithEmailAndPassword,
  GoogleAuthProvider,
  signInWithEmailAndPassword,
  signInWithPopup,
  updateProfile,
} from "firebase/auth";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { getClientAuth } from "@/lib/firebaseClient";

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

function mapFirebaseError(message: string): string {
  if (message.includes("auth/invalid-credential") || message.includes("auth/wrong-password")) {
    return "Email or password is not correct. Try again.";
  }
  if (message.includes("auth/email-already-in-use")) {
    return "That email already has an account. Try logging in.";
  }
  if (message.includes("auth/weak-password")) {
    return "Use a stronger password (at least 6 characters).";
  }
  if (message.includes("auth/popup-closed-by-user")) {
    return "Sign-in was cancelled.";
  }
  return "Something went wrong. Please try again.";
}

export default function AuthPage() {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    const trimmedEmail = email.trim();
    const trimmedName = name.trim();

    if (!trimmedEmail) {
      setError("Please enter your email.");
      return;
    }
    if (!password) {
      setError("Please enter a password.");
      return;
    }
    if (mode === "signup") {
      if (!trimmedName) {
        setError("Please enter your name.");
        return;
      }
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
        await updateProfile(cred.user, { displayName: trimmedName });
      } else {
        await signInWithEmailAndPassword(auth, trimmedEmail, password);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Error";
      setError(mapFirebaseError(message));
    } finally {
      setBusy(false);
    }
  };

  const handleGoogle = async () => {
    setError(null);
    setBusy(true);
    try {
      const auth = getClientAuth();
      const provider = new GoogleAuthProvider();
      await signInWithPopup(auth, provider);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Error";
      setError(mapFirebaseError(message));
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
              {mode === "signup" && (
                <div>
                  <label htmlFor="auth-name" className="mb-2 block text-lg font-semibold text-stone-900">
                    Your name
                  </label>
                  <Input
                    id="auth-name"
                    name="name"
                    autoComplete="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Alex Carter"
                    className={authInputClass}
                  />
                </div>
              )}

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
