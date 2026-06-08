import type { Metadata } from 'next';
import { Navbar } from '@/components/Navbar';
import { Footer } from '@/components/Footer';
import { ServiceCards } from '@/components/ServiceCards';
import { ProcessSteps } from '@/components/ProcessSteps';
import { SITE_NAME } from '@/lib/content';

export const metadata: Metadata = {
  title: `Services | ${SITE_NAME}`,
  description:
    'Web design, mobile apps, brand messaging, and digital advertising for mission-driven organizations.',
};

export default function ServicesPage() {
  return (
    <>
      <Navbar />
      <main>
        <section className="section pt-16 md:pt-24">
          <div className="container-narrow text-center">
            <p className="eyebrow">Services</p>
            <h1 className="text-pretty">How I Help You Achieve Your Mission</h1>
            <p className="mt-4 text-lg text-muted text-pretty">
              For organizations and businesses who care about presenting their
              purpose beautifully. Merimee Digital Solutions simplifies web
              design, apps, and marketing so you can focus on your mission.
            </p>
          </div>
        </section>
        <ServiceCards />
        <ProcessSteps />
      </main>
      <Footer />
    </>
  );
}
