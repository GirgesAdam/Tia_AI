import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Data Deletion Instructions | Tia AI",
  description:
    "Instructions for requesting deletion of personal data associated with Tia AI services.",
};

export default function DataDeletionPage() {
  const legalName = process.env.NEXT_PUBLIC_TIA_LEGAL_NAME?.trim() || "Tia AI";
  const privacyEmail = process.env.NEXT_PUBLIC_PRIVACY_CONTACT_EMAIL?.trim();

  return (
    <main className="min-h-screen bg-[var(--bg)] px-4 py-8 sm:px-6 sm:py-12">
      <div className="mx-auto max-w-3xl">
        <article className="rounded-3xl border border-[var(--border)] bg-[var(--surface)] p-6 shadow-sm sm:p-9">
          <div className="space-y-3 border-b border-[var(--border)] pb-7">
            <p className="text-sm font-semibold text-[var(--accent)]">Tia AI</p>
            <h1 className="text-3xl font-bold tracking-tight text-[var(--text)] sm:text-4xl">
              Data Deletion Instructions
            </h1>
            <p className="text-sm leading-7 text-[var(--muted)] sm:text-base">
              These instructions explain how to request deletion of personal data
              associated with {legalName} and a Tia AI workspace.
            </p>
          </div>

          <div className="space-y-8 pt-7 text-sm leading-7 text-[var(--muted)] sm:text-[15px]">
            <section className="space-y-3">
              <h2 className="text-xl font-semibold text-[var(--text)]">
                Customer data held by a clinic or business
              </h2>
              <p>
                If you contacted a clinic or business through WhatsApp or another
                channel connected to Tia AI, please first contact that clinic or
                business using its published contact details. The clinic or business
                operating the workspace controls the customer relationship and can
                identify the relevant conversation, CRM record, or appointment.
              </p>
            </section>

            <section className="space-y-3 border-t border-[var(--border)] pt-7">
              <h2 className="text-xl font-semibold text-[var(--text)]">
                Tia AI platform requests
              </h2>
              {privacyEmail ? (
                <p>
                  To request deletion of data associated with the Tia AI platform,
                  email{" "}
                  <a
                    className="font-medium text-[var(--accent)] underline underline-offset-4"
                    href={`mailto:${privacyEmail}?subject=Tia%20AI%20Data%20Deletion%20Request`}
                  >
                    {privacyEmail}
                  </a>
                  {" "}with the subject <strong>Data Deletion Request</strong>. Do not
                  include passwords, access tokens, or unnecessary medical details.
                </p>
              ) : (
                <p>
                  Workspace administrators should submit a deletion request through
                  their normal Tia AI support channel. Customers should contact the
                  clinic or business they interacted with using that organization&apos;s
                  published contact details.
                </p>
              )}
            </section>

            <section className="space-y-3 border-t border-[var(--border)] pt-7">
              <h2 className="text-xl font-semibold text-[var(--text)]">
                What to include
              </h2>
              <ul className="list-disc space-y-2 pr-5 marker:text-[var(--accent)]">
                <li>Your name and a reliable way to contact you.</li>
                <li>
                  The clinic or business workspace involved, if the request relates
                  to customer data.
                </li>
                <li>
                  The phone number or email address used in the relevant interaction,
                  when needed to locate the record.
                </li>
                <li>A clear description of the data you want deleted.</li>
              </ul>
            </section>

            <section className="space-y-3 border-t border-[var(--border)] pt-7">
              <h2 className="text-xl font-semibold text-[var(--text)]">
                Verification and completion
              </h2>
              <p>
                We or the responsible clinic/business may request reasonable
                verification before acting on a deletion request so that information
                is not deleted at the request of an unauthorized person. After the
                request is verified, applicable data will be deleted or anonymized
                where appropriate, subject to records that must be retained for
                security, fraud prevention, legal obligations, dispute resolution,
                or other lawful purposes.
              </p>
            </section>

            <section className="space-y-3 border-t border-[var(--border)] pt-7">
              <h2 className="text-xl font-semibold text-[var(--text)]">
                Related privacy information
              </h2>
              <p>
                For more information about the categories of information processed
                and how they are used, read the{" "}
                <Link
                  className="font-medium text-[var(--accent)] underline underline-offset-4"
                  href="/privacy"
                >
                  Tia AI Privacy Policy
                </Link>
                .
              </p>
            </section>
          </div>
        </article>
      </div>
    </main>
  );
}
