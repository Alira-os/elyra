import type { Metadata } from 'next';
import { Navbar } from '@/components/Navbar';
import { Footer } from '@/components/Footer';
import { ContactForm } from '@/components/ContactForm';
import { CONTACT_INFO, SITE_NAME } from '@/lib/content';

export const metadata: Metadata = {
  title: `Contact | ${SITE_NAME}`,
  description:
    "Let's start a conversation. Reach out about your project and I'll respond within 48 hours.",
};

export default function ContactPage() {
  return (
    <>
      <Navbar />
      <main>
        <section className="section pt-16 md:pt-24">
          <div className="container-narrow">
            <div className="text-center mb-10">
              <p className="eyebrow">Contact</p>
              <h1 className="text-pretty">Let's Talk</h1>
              <p className="mt-3 text-muted text-pretty">
                I'd love to hear from you. Share a bit about your project and
                I'll respond within 48 hours.
              </p>
            </div>
            <ContactForm />
            <div className="mt-12 grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm text-muted text-center sm:text-left">
              <div>
                <p className="font-semibold text-primary">Email</p>
                <a
                  href={`mailto:${CONTACT_INFO.email}`}
                  className="text-accent hover:underline"
                >
                  {CONTACT_INFO.email}
                </a>
              </div>
              <div>
                <p className="font-semibold text-primary">Phone</p>
                <a
                  href={`tel:${CONTACT_INFO.phone.replace(/[^\d+]/g, '')}`}
                  className="text-accent hover:underline"
                >
                  {CONTACT_INFO.phone}
                </a>
              </div>
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
