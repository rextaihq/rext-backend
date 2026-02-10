# Task 155: Remove Unused Frontend Subscription Components and Dead Exports

## Metadata
- **Task ID:** TASK-155
- **Source:** B5 - Subscription & Billing (Finding #36 under P3 Low)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P3 Low
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `rext-admin/components/subscription/` directory contains four exported components and one interface prop that are defined but never imported or rendered anywhere in the application. Specifically:

1. **`TrialConversionCTA`** in `trial-conversion-cta.tsx` (180 lines) — A fully-implemented trial conversion call-to-action component with urgency messaging, benefits list, and upgrade buttons. Despite being feature-complete, it is never imported or used by any page or component in the entire `rext-admin` codebase.

2. **`CheckoutLink`** in `checkout-button.tsx` (lines 120–156) — A companion export alongside `CheckoutButton`. While `CheckoutButton` is actively used in `checkout-with-discount.tsx` and tests, `CheckoutLink` (which uses LemonSqueezy's automatic `lemonsqueezy-button` class detection) has zero imports anywhere in the project.

3. **`CustomerPortalIconButton`** in `customer-portal-button.tsx` (lines 159–177) — An icon-only variant of `CustomerPortalButton`. The base `CustomerPortalButton` is used in subscription and billing pages, but this compact icon variant is never imported.

4. **`CustomerPortalLink`** in `customer-portal-button.tsx` (lines 183–203) — A text-link variant of `CustomerPortalButton` for inline usage. Like the icon variant, it is never imported anywhere.

5. **`showGlobally` prop** on `TrialStatusBanner` in `trial-status-banner.tsx` (line 41) — This prop is declared in the `TrialStatusBannerProps` interface and is passed as `showGlobally={false}` in 3 locations (`pricing/page.tsx`, `settings/subscription/page.tsx`, `subscription/page.tsx`), but the component's implementation **never references or uses this prop value**. It is destructured out and discarded — the banner's visibility is controlled entirely by subscription status and `isDismissed` state, not by `showGlobally`.

While modern bundlers like Webpack (used by Next.js 16.x) perform tree-shaking on unused exports in production builds, tree-shaking is not guaranteed for all code patterns — especially components with side effects, `"use client"` directives, or complex import chains. More importantly, these unused exports create maintenance overhead: developers must understand, review, and potentially update code that serves no purpose. The `TrialConversionCTA` alone is 180 lines of dead code that could mislead developers into thinking it's an active part of the UI.

---

## Current Code

### TrialConversionCTA (entire file is unused)

```tsx
// File: rext-admin/components/subscription/trial-conversion-cta.tsx
// Lines: 1-180 (entire file)
"use client";

import { Check, Sparkles, X, Zap } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useSubscriptionStore } from "@/stores/subscription-store";
import { SubscriptionStatus } from "@/types/subscription";

export interface TrialConversionCTAProps {
  className?: string;
  variant?: "inline" | "modal";
  onDismiss?: () => void;
  dismissible?: boolean;
}

export function TrialConversionCTA({ ... }) {
  // 180 lines of fully-implemented but unused component
}
```

### CheckoutLink (unused export in checkout-button.tsx)

```tsx
// File: rext-admin/components/subscription/checkout-button.tsx
// Lines: 120-156
export interface CheckoutLinkProps {
  checkoutUrl: string;
  children?: React.ReactNode;
  className?: string;
}

export function CheckoutLink({
  checkoutUrl,
  children = "Subscribe Now",
  className,
}: CheckoutLinkProps) {
  // ... unused variant
}
```

### CustomerPortalIconButton and CustomerPortalLink (unused exports)

```tsx
// File: rext-admin/components/subscription/customer-portal-button.tsx
// Lines: 159-203
export function CustomerPortalIconButton({ ... }) {
  // icon-only variant — never imported
}

export function CustomerPortalLink({ ... }) {
  // text-link variant — never imported
}
```

### showGlobally prop (declared but never consumed)

```tsx
// File: rext-admin/components/subscription/trial-status-banner.tsx
// Lines: 25-47
interface TrialStatusBannerProps {
  showWhenDaysRemaining?: number;
  className?: string;
  showGlobally?: boolean;  // <-- declared but never used in component logic
}

export function TrialStatusBanner({
  showWhenDaysRemaining = 0,
  className = "",
  // showGlobally is NOT destructured — it's silently ignored
}: TrialStatusBannerProps) {
```

---

## Why This Matters (Context & Reasoning)

The subscription components are part of the billing and subscription management UI, which is a critical revenue path for Rext AI. These unused components create several problems:

1. **Maintenance burden:** When subscription-related types, stores, or APIs change, developers must update these unused components to prevent type errors during builds, wasting time on code that has no user-facing impact.

2. **Developer confusion:** A new developer seeing `TrialConversionCTA` might assume it's rendered somewhere and spend time debugging why changes to it don't appear in the UI.

3. **False confidence:** The `showGlobally` prop is passed in 3 locations with the value `false`, but since the component never reads it, the prop has no effect. Developers passing this prop believe they're controlling behavior that doesn't exist.

4. **Bundle size risk:** While Next.js tree-shakes unused exports, the `TrialConversionCTA` file is a standalone module with `"use client"` — it may not be fully eliminated if any tooling or dynamic import references the file path.

5. **Test overhead:** If tests are ever written for these components, they would test functionality that is never exercised in production.

---

## Impact

- **Severity:** Low — no runtime errors or user-visible bugs. Dead code increases maintenance cost and cognitive overhead.
- **Affected Users/Flows:** No users are directly affected since the code is never rendered.
- **Blast Radius:** Isolated to the `components/subscription/` directory. Removing these components has zero risk of breaking existing functionality since they are confirmed to have zero imports.

---

## Recommended Solution

### Step 1: Delete `trial-conversion-cta.tsx`

Since this entire file (180 lines) has zero imports anywhere in the codebase, delete it entirely.

```bash
# File to delete: rext-admin/components/subscription/trial-conversion-cta.tsx
rm rext-admin/components/subscription/trial-conversion-cta.tsx
```

### Step 2: Remove `CheckoutLink` and `CheckoutLinkProps` from `checkout-button.tsx`

Remove the unused `CheckoutLink` component and its interface from `checkout-button.tsx`, keeping only `CheckoutButton` and `CheckoutButtonProps` which are actively used.

```tsx
// File: rext-admin/components/subscription/checkout-button.tsx
// DELETE lines 114-156 (the CheckoutLink section)
// Keep everything from line 1-112 (CheckoutButton and CheckoutButtonProps)
```

The file should end after the `CheckoutButton` component's closing brace (line 112).

### Step 3: Remove `CustomerPortalIconButton` and `CustomerPortalLink` from `customer-portal-button.tsx`

Remove the two unused variant exports, keeping only `CustomerPortalButton` which is actively used.

```tsx
// File: rext-admin/components/subscription/customer-portal-button.tsx
// DELETE lines 155-203 (CustomerPortalIconButton and CustomerPortalLink)
// Keep everything from line 1-153 (CustomerPortalButton and its interface)
```

The file should end after the `CustomerPortalButton` component's closing brace (line 153).

### Step 4: Remove `showGlobally` prop from `TrialStatusBanner`

Remove the `showGlobally` prop from the interface and remove the prop from all 3 call sites.

```tsx
// File: rext-admin/components/subscription/trial-status-banner.tsx
// Remove from interface (line 41):
interface TrialStatusBannerProps {
  showWhenDaysRemaining?: number;
  className?: string;
  // DELETE: showGlobally?: boolean;
}
```

Then remove the prop from the 3 call sites:

```tsx
// File: rext-admin/app/pricing/page.tsx
// Change: <TrialStatusBanner showGlobally={false} />
// To:     <TrialStatusBanner />

// File: rext-admin/app/settings/subscription/page.tsx
// Change: <TrialStatusBanner showGlobally={false} />
// To:     <TrialStatusBanner />

// File: rext-admin/app/subscription/page.tsx
// Change: <TrialStatusBanner showGlobally={false} />
// To:     <TrialStatusBanner />
```

### Step 5: Verify no test files reference the removed exports

Check if any test files import the removed components:

```bash
grep -r "CheckoutLink\|CustomerPortalIconButton\|CustomerPortalLink\|TrialConversionCTA" rext-admin/__tests__/
```

If any tests reference these, remove the test cases as well.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-admin/app/pricing/page.tsx` | ~84 | Passes `showGlobally={false}` to `TrialStatusBanner` — remove prop |
| `rext-admin/app/settings/subscription/page.tsx` | ~81 | Passes `showGlobally={false}` to `TrialStatusBanner` — remove prop |
| `rext-admin/app/subscription/page.tsx` | ~158 | Passes `showGlobally={false}` to `TrialStatusBanner` — remove prop |
| `rext-admin/__tests__/components/subscription/checkout-button.test.tsx` | varies | May import `CheckoutLink` — verify and remove if so |
| `rext-admin/__tests__/components/subscription/customer-portal-button.test.tsx` | varies | May test `CustomerPortalIconButton` / `CustomerPortalLink` — verify and remove if so |

---

## Testing Instructions

### Before Fix (Confirm Dead Code):

1. Search the codebase for any import of the components:
   ```bash
   grep -rn "TrialConversionCTA" rext-admin/app/ rext-admin/components/ rext-admin/lib/
   grep -rn "CheckoutLink" rext-admin/app/ rext-admin/components/ rext-admin/lib/
   grep -rn "CustomerPortalIconButton" rext-admin/app/ rext-admin/components/ rext-admin/lib/
   grep -rn "CustomerPortalLink" rext-admin/app/ rext-admin/components/ rext-admin/lib/
   ```
   Expected: Zero results for all four (confirming they are unused).

2. Search for `showGlobally` usage in the `TrialStatusBanner` component implementation:
   ```bash
   grep -n "showGlobally" rext-admin/components/subscription/trial-status-banner.tsx
   ```
   Expected: Only appears in the interface definition (line 41), not in any conditional logic.

### After Fix (Verify Removal):

1. Run the TypeScript compiler to ensure no type errors:
   ```bash
   cd rext-admin && npx tsc --noEmit
   ```
   Expected: No errors. If any file imported the removed exports, this will catch it.

2. Run the build:
   ```bash
   cd rext-admin && npm run build
   ```
   Expected: Build succeeds without errors.

3. Run existing tests:
   ```bash
   cd rext-admin && npm test
   ```
   Expected: All existing tests pass.

4. Verify the `TrialStatusBanner` still renders correctly on pricing, subscription, and settings/subscription pages by visiting each page in the browser while on a trial subscription.

### Run Existing Tests:
```bash
cd rext-admin && npm test -- --testPathPattern="subscription"
```

---

## Acceptance Criteria

- [ ] `trial-conversion-cta.tsx` file is deleted
- [ ] `CheckoutLink` and `CheckoutLinkProps` exports removed from `checkout-button.tsx`
- [ ] `CustomerPortalIconButton` and `CustomerPortalLink` exports removed from `customer-portal-button.tsx`
- [ ] `showGlobally` prop removed from `TrialStatusBannerProps` interface
- [ ] `showGlobally={false}` prop removed from all 3 call sites
- [ ] TypeScript compilation succeeds with `tsc --noEmit`
- [ ] Production build succeeds with `npm run build`
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Next.js Code Splitting](https://nextjs.org/docs/app/building-your-application/optimizing/lazy-loading) — Next.js automatically code-splits pages but unused exports within imported modules may still be bundled
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Knip — Find Unused Exports](https://knip.dev/) — Recommended tool for automated detection of unused files, exports, and dependencies in TypeScript projects. Consider adding to CI pipeline.
- **Related Issues/PRs:** [Webpack Tree Shaking Guide](https://webpack.js.org/guides/tree-shaking/) — Explains how tree-shaking works and its limitations with side-effect-ful modules

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-140 (Stripe Remnants in Frontend Types — also dead frontend code), TASK-153 (Billing Page Uses DELETE for Cancel — involves legacy billing page which may reference unused components)
