import { ShieldAlert, User } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import type { UserRole } from "./AuthPage";

type Props = {
  careRecipientName: string;
  caregiverName: string;
  onChooseRole: (role: UserRole) => void;
  onSignOut: () => void;
};

export default function RoleSelectPage({
  careRecipientName,
  caregiverName,
  onChooseRole,
  onSignOut,
}: Props) {
  return (
    <div className="min-h-screen p-4 pb-12 md:flex md:items-center md:justify-center md:p-8">
      <div className="mx-auto w-full max-w-2xl">
        <header className="mb-8 text-center">
          <p className="text-sm font-bold uppercase tracking-widest text-amber-200">C.A.R.E</p>
          <h1 className="mt-2 text-3xl font-bold text-white md:text-4xl">Who is using the app?</h1>
          <p className="mt-2 text-lg text-amber-100">
            User: <span className="font-bold text-white">{careRecipientName}</span>
            {" · "}
            Caregiver: <span className="font-bold text-white">{caregiverName}</span>
          </p>
          <p className="mt-1 text-base text-amber-100/90">Pick who is using the app right now.</p>
        </header>

        <div className="flex flex-col gap-6 md:flex-row md:items-stretch">
          {/* Caregiver */}
          <Card className="flex-1 rounded-3xl border-2 border-stone-700 bg-[#f5ebe0] shadow-lg">
            <CardContent className="flex h-full flex-col p-6 md:p-8">
              <div className="mb-4 flex justify-center">
                <div className="rounded-2xl border-2 border-stone-600 bg-blue-900 p-4 text-white">
                  <ShieldAlert className="h-12 w-12 md:h-14 md:w-14" strokeWidth={2} aria-hidden />
                </div>
              </div>
              <h2 className="text-center text-2xl font-bold text-stone-950">Caregiver</h2>
              <p className="mt-3 flex-1 text-center text-lg font-medium leading-relaxed text-stone-800">
                For family or staff helping with meals: controls, timing, and bite tracking.
              </p>
              <Button
                type="button"
                className="mt-6 h-16 w-full rounded-2xl border-2 border-blue-950 bg-blue-900 text-lg font-semibold text-white hover:bg-blue-950"
                onClick={() => onChooseRole("caregiver")}
              >
                Continue as caregiver
              </Button>
            </CardContent>
          </Card>

          {/* User */}
          <Card className="flex-1 rounded-3xl border-2 border-stone-700 bg-[#f5ebe0] shadow-lg">
            <CardContent className="flex h-full flex-col p-6 md:p-8">
              <div className="mb-4 flex justify-center">
                <div className="rounded-2xl border-2 border-stone-600 bg-stone-800 p-4 text-white">
                  <User className="h-12 w-12 md:h-14 md:w-14" strokeWidth={2} aria-hidden />
                </div>
              </div>
              <h2 className="text-center text-2xl font-bold text-stone-950">User</h2>
              <p className="mt-3 flex-1 text-center text-lg font-medium leading-relaxed text-stone-800">
                For the person eating: simple choices for food and a clear bite count.
              </p>
              <Button
                type="button"
                className="mt-6 h-16 w-full rounded-2xl border-2 border-stone-700 bg-stone-800 text-lg font-semibold text-white hover:bg-stone-900"
                onClick={() => onChooseRole("user")}
              >
                Continue as user
              </Button>
            </CardContent>
          </Card>
        </div>

        <p className="mt-8 text-center">
          <button
            type="button"
            className="text-lg font-medium text-amber-100 underline underline-offset-4 hover:text-white"
            onClick={onSignOut}
          >
            Sign out
          </button>
        </p>
      </div>
    </div>
  );
}
