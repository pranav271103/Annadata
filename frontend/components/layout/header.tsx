"use client";

import { Search, Bell, Menu, User, ChevronDown, LogOut, Languages } from "lucide-react";
import { cn } from "@/lib/utils";
import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { useAuthStore } from "@/store/auth-store";
import { useLanguageStore } from "@/store/language-store";

interface HeaderProps {
  onMenuClick: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  const router = useRouter();
  const { user, isAuthenticated, logout } = useAuthStore();
  const { language, setLanguage, t } = useLanguageStore();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  const displayName = user?.full_name || user?.email || "User";
  const displayRole = user?.role
    ? user.role.charAt(0).toUpperCase() + user.role.slice(1)
    : "";

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        userMenuRef.current &&
        !userMenuRef.current.contains(event.target as Node)
      ) {
        setUserMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function handleSignOut() {
    logout();
    setUserMenuOpen(false);
    router.push("/auth");
  }

  return (
    <header className="flex h-16 items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)] px-4 lg:px-6">
      {/* Left: hamburger + search */}
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuClick}
          className="rounded-md p-2 text-[var(--color-text-muted)] hover:bg-[var(--color-border)] lg:hidden"
        >
          <Menu className="h-5 w-5" />
        </button>

        <div className="relative hidden sm:block">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-muted)]" />
          <input
            type="text"
            placeholder="Search..."
            className="h-9 w-64 rounded-lg border border-[var(--color-border)] bg-[var(--color-background)] pl-9 pr-3 text-sm text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] outline-none focus:border-[var(--color-primary)] focus:ring-1 focus:ring-[var(--color-primary)]"
          />
        </div>
      </div>

      {/* Right: notifications + user */}
      <div className="flex items-center gap-2">
        {/* Mobile search */}
        <button className="rounded-md p-2 text-[var(--color-text-muted)] hover:bg-[var(--color-border)] sm:hidden">
          <Search className="h-5 w-5" />
        </button>

        {/* Theme toggle */}
        <ThemeToggle />

        {/* Language toggle */}
        <button
          onClick={() => setLanguage(language === "en" ? "hi" : "en")}
          className="flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] px-2.5 py-1.5 text-xs font-medium text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors"
          title={language === "en" ? "हिन्दी में बदलें" : "Switch to English"}
        >
          <Languages className="h-4 w-4" />
          <span>{language === "en" ? "हिन्दी" : "EN"}</span>
        </button>

        {/* Notification bell */}
        <button className="relative rounded-md p-2 text-[var(--color-text-muted)] hover:bg-[var(--color-border)]">
          <Bell className="h-5 w-5" />
          <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-[var(--color-error)]" />
        </button>

        {/* User dropdown */}
        {isAuthenticated ? (
          <div ref={userMenuRef} className="relative">
            <button
              onClick={() => setUserMenuOpen(!userMenuOpen)}
              className="flex items-center gap-2 rounded-lg p-1.5 hover:bg-[var(--color-border)]"
            >
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--color-primary)]/10">
                <User className="h-4 w-4 text-[var(--color-primary)]" />
              </div>
              <div className="hidden flex-col items-start md:flex">
                <span className="text-sm font-medium text-[var(--color-text)]">
                  {displayName}
                </span>
                {displayRole && (
                  <span className="text-xs text-[var(--color-text-muted)]">
                    {displayRole}
                  </span>
                )}
              </div>
              <ChevronDown className="hidden h-4 w-4 text-[var(--color-text-muted)] md:block" />
            </button>

            {userMenuOpen && (
              <div className="absolute right-0 top-full mt-1 w-48 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] py-1 shadow-lg">
                <a
                  href="/dashboard/settings"
                  className="block px-4 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-border)]"
                >
                  Profile
                </a>
                <a
                  href="/dashboard/settings"
                  className="block px-4 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-border)]"
                >
                  Settings
                </a>
                <div className="my-1 border-t border-[var(--color-border)]" />
                <button
                  onClick={handleSignOut}
                  className="flex w-full items-center gap-2 px-4 py-2 text-left text-sm text-[var(--color-error)] hover:bg-[var(--color-border)]"
                >
                  <LogOut className="h-4 w-4" />
                  Sign out
                </button>
              </div>
            )}
          </div>
        ) : (
          <button
            onClick={() => router.push("/auth")}
            className="rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white hover:opacity-90"
          >
            Sign In
          </button>
        )}
      </div>
    </header>
  );
}
