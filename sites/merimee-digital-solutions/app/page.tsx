import { Header } from '@/components/Header';
import { Hero } from '@/components/Hero';
import { Services } from '@/components/Services';
import { Portfolio } from '@/components/Portfolio';
import { Testimonials } from '@/components/Testimonials';
import { About } from '@/components/About';
import { Contact } from '@/components/Contact';
import { Footer } from '@/components/Footer';

export default function HomePage() {
  return (
    <>
      <Header />
      <main id="main">
        <Hero
          title="Beautiful websites for mission-driven organizations."
          subtitle="I help Catholic schools, nonprofits, and small-but-mighty teams build the website they wish they had \u2014 modern, fast, and unmistakably yours."
        />
        <Services />
        <Portfolio />
        <About
          body="I run a small, intentional studio focused on one thing: helping mission-driven organizations show up on the web the way they actually are. You\u2019ll work with me directly \u2014 no account managers, no junior team, no templated proposals. Just thoughtful design, modern technology, and a partner who cares about getting it right."
        />
        <Testimonials />
        <Contact />
      </main>
      <Footer />
    </>
  );
}
