"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { navLinks, siteContent } from "@/lib/content";
import { ThemeToggle } from "./ThemeToggle";

export function Navigation() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={
        "motion-subtle fixed inset-x-0 top-0 z-40 " +
        (scrolled
          ? "border-b border-border bg-background/90 backdrop-blur-md shadow-sm"
          : "bg-transparent")
      }
    >
      <div className="container-wide flex h-16 items-center justify-between gap-4 md:h-20">
        <Link
          href="#top"
          className="motion-subtle flex items-center gap-2 text-base font-semibold tracking-tight text-foreground hover:text-accent md:text-lg"
          aria-label={`${siteContent.brand.name} home`}
        >
          <span
            aria-hidden="true"
            className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-primary text-background font-heading text-base"
          >
            M
          </span>
          <span className="hidden font-heading sm:inline">
            {siteContent.brand.shortName}
          </span>
        </Link>

        <nav
          aria-label="Primary"
          className="hidden items-center gap-1 md:flex"
        >
          {navLinks.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="motion-subtle rounded-md px-3 py-2 text-sm font-medium text-foreground/80 hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              {link.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <ThemeToggle />
          <a
            href="#contact"
            className="btn-primary motion-classical hidden md:inline-flex"
          >
            {siteContent.hero.primaryCta.label}
          </a>
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            aria-controls="mobile-nav"
            className="motion-subtle inline-flex h-10 w-10 items-center justify-center rounded-md text-foreground hover:bg-surface md:hidden"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              {open ? (
                <path d="M18 6 6 18M6 6l12 12" />
              ) : (
                <>
                  <line x1="3" y1="6" x2="21" y2="6" />
                  <line x1="3" y1="12" x2="21" y2="12" />
                  <line x1="3" y1="18" x2="21" y2="18" />
                </>
              )}
            </svg>
          </button>
        </div>
      </div>

      {open && (
        <div
          id="mobile-nav"
          className="border-t border-border bg-background md:hidden"
        >
          <nav
            aria-label="Mobile"
            className="container-wide flex flex-col gap-1 py-4"
          >
            {navLinks.map((link) => (
              <a
                key={link.href}
                href={link.href}
                onClick={() => setOpen(false)}
                className="motion-subtle rounded-md px-3 py-3 text-base font-medium text-foreground/80 hover:bg-surface hover:text-accent"
              >
                {link.label}
              </a>
            ))}
            <a
              href="#contact"
              onClick={() => setOpen(false)}
              className="btn-primary motion-classical mt-2 w-full"
            >
              {siteContent.hero.primaryCta.label}
            </a>
          </nav>
        </div>
      )}
    </header>
  );
}
