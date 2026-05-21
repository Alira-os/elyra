import React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const contactSchema = z.object({
  firstName: z.string().min(1, 'First name required'),
  lastName: z.string().min(1, 'Last name required'),
  companyName: z.string().optional(),
  topic: z.string().min(5, 'Please share a brief topic'),
  email: z.string().email('Valid email required'),
  phone: z.string().optional(),
});

type ContactFormData = z.infer<typeof contactSchema>;

function ContactForm() {
  const { register, handleSubmit, formState: { errors, isSubmitting }, reset } = useForm<ContactFormData>({
    resolver: zodResolver(contactSchema),
  });
  const [success, setSuccess] = React.useState(false);

  const onSubmit = async (data: ContactFormData) => {
    const res = await fetch('/api/contact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (res.ok) {
      setSuccess(true);
      reset();
      setTimeout(() => setSuccess(false), 4000);
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <input {...register('firstName')} placeholder="First name" className="w-full bg-white/10 border border-white/20 p-4 rounded-lg placeholder:text-white/50 focus:outline-none focus:border-[#6366F1] focus:ring-1 focus:ring-[#6366F1] transition-all" />
          {errors.firstName && <p className="text-red-400 text-sm mt-1">{errors.firstName.message}</p>}
        </div>
        <div>
          <input {...register('lastName')} placeholder="Last name" className="w-full bg-white/10 border border-white/20 p-4 rounded-lg placeholder:text-white/50 focus:outline-none focus:border-[#6366F1] focus:ring-1 focus:ring-[#6366F1] transition-all" />
          {errors.lastName && <p className="text-red-400 text-sm mt-1">{errors.lastName.message}</p>}
        </div>
      </div>
      <input {...register('companyName')} placeholder="Company name (optional)" className="w-full bg-white/10 border border-white/20 p-4 rounded-lg placeholder:text-white/50 focus:outline-none focus:border-[#6366F1] focus:ring-1 focus:ring-[#6366F1] transition-all" />
      <div>
        <input {...register('topic')} placeholder="My website, an app idea, connecting with people, etc..." className="w-full bg-white/10 border border-white/20 p-4 rounded-lg placeholder:text-white/50 focus:outline-none focus:border-[#6366F1] focus:ring-1 focus:ring-[#6366F1] transition-all" />
        {errors.topic && <p className="text-red-400 text-sm mt-1">{errors.topic.message}</p>}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <input {...register('email')} type="email" placeholder="Email" className="w-full bg-white/10 border border-white/20 p-4 rounded-lg placeholder:text-white/50 focus:outline-none focus:border-[#6366F1] focus:ring-1 focus:ring-[#6366F1] transition-all" />
          {errors.email && <p className="text-red-400 text-sm mt-1">{errors.email.message}</p>}
        </div>
        <input {...register('phone')} type="tel" placeholder="Phone" className="w-full bg-white/10 border border-white/20 p-4 rounded-lg placeholder:text-white/50 focus:outline-none focus:border-[#6366F1] focus:ring-1 focus:ring-[#6366F1] transition-all" />
      </div>
      <button type="submit" disabled={isSubmitting} className="w-full py-4 bg-white text-[#1E3A5F] rounded-full font-medium hover:bg-[#EEF2FF] active:scale-[0.985] transition-all disabled:opacity-70">
        {isSubmitting ? 'Sending...' : 'Send Message'}
      </button>
      {success && <p className="text-center text-[#A5B4C8] mt-4">Thank you. I'll be in touch soon.</p>}
    </form>
  );
}

export default function MerimeeDigitalSolutions() {
  return (
    <div className="min-h-screen bg-[#F8FAFC] text-[#1E293B] font-sans">
      {/* Navigation */}
      <nav className="sticky top-0 z-50 bg-white/95 backdrop-blur border-b border-[#EEF2FF]">
        <div className="max-w-6xl mx-auto px-6 flex justify-between items-center h-20">
          <div className="font-serif text-2xl tracking-tight text-[#1E3A5F]">Merimee Digital Solutions</div>
          <div className="flex gap-8 text-sm">
            <a href="#services" className="hover:text-[#1E3A5F] transition-colors">Services</a>
            <a href="#process" className="hover:text-[#1E3A5F] transition-colors">Process</a>
            <a href="#portfolio" className="hover:text-[#1E3A5F] transition-colors">Portfolio</a>
            <a href="#about" className="hover:text-[#1E3A5F] transition-colors">About</a>
            <a href="#contact" className="px-5 py-2 bg-[#1E3A5F] text-white rounded-full text-sm hover:bg-[#162d4a] transition-all">Let's Talk</a>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative h-[90vh] flex items-center justify-center bg-[#1E3A5F] text-white overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(#ffffff10_1px,transparent_1px)] bg-[length:4px_4px]"></div>
        <div className="relative z-10 max-w-4xl px-6 text-center">
          <h1 className="font-serif text-6xl md:text-7xl tracking-[-2px] mb-6">Showcase Your Mission</h1>
          <p className="text-2xl text-[#A5B4C8] mb-10 max-w-lg mx-auto">Simplified Web &amp; Marketing Solutions</p>
          <a href="#contact" className="inline-block px-10 py-4 bg-white text-[#1E3A5F] rounded-full font-medium text-lg hover:bg-[#EEF2FF] transition-all">Let's Talk</a>
        </div>
      </section>

      {/* Services */}
      <section id="services" className="max-w-6xl mx-auto px-6 py-20">
        <h2 className="font-serif text-4xl mb-4 text-center">How Can I Help You?</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mt-10">
          {[
            { title: "Web Design", desc: "Beautiful, mission-aligned websites" },
            { title: "Mobile Apps", desc: "Purpose-driven mobile experiences" },
            { title: "Brand Messaging", desc: "Clarify and communicate your cause" },
            { title: "Build Interest", desc: "Strategic marketing that resonates" }
          ].map((service, i) => (
            <div key={i} className="card p-8 border border-[#EEF2FF]">
              <div className="w-12 h-12 bg-[#EEF2FF] rounded-full mb-6"></div>
              <h3 className="font-serif text-2xl mb-3">{service.title}</h3>
              <p className="text-[#475569]">{service.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Process */}
      <section id="process" className="bg-white py-20 border-y">
        <div className="max-w-5xl mx-auto px-6">
          <h2 className="font-serif text-4xl mb-12 text-center">Clarify Your Cause</h2>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              { step: "01", title: "Schedule a Call", text: "Reach out and discover how we might work together and find a solution." },
              { step: "02", title: "Craft a Plan", text: "Let's put together an effective plan for realizing your goals and creating something beautiful." },
              { step: "03", title: "Realize Your Vision", text: "Don't resign yourself to mediocrity. Let's be great together." }
            ].map((p, i) => (
              <div key={i} className="flex gap-6">
                <div className="font-mono text-5xl text-[#6366F1] font-light tabular-nums">{p.step}</div>
                <div>
                  <h3 className="font-serif text-2xl mb-3">{p.title}</h3>
                  <p className="text-[#475569]">{p.text}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Portfolio */}
      <section id="portfolio" className="max-w-6xl mx-auto px-6 py-20">
        <h2 className="font-serif text-4xl mb-10 text-center">Featured Projects</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          {[
            { name: "Holy Rollers", type: "Website Design, Messaging", url: "https://www.holyrollers.us/" },
            { name: "Chesterton Academy of Akron", type: "Web Redesign, Building Interest", url: "https://akronchestertonacademy.org/" },
            { name: "Parker Eidle", type: "Website Design", url: "https://www.parkereidle.com/" },
            { name: "Alena Carter", type: "Website Design, Messaging", url: "http://www.alenacarter.art" },
            { name: "Bonfire Media", type: "Website Design, Messaging, Building Interest", url: "https://www.bonfiremedia.art/" }
          ].map((project, idx) => (
            <a key={idx} href={project.url} target="_blank" rel="noopener noreferrer" className="group block aspect-[16/10] bg-[#1E3A5F] rounded-xl overflow-hidden relative">
              <div className="absolute inset-0 bg-gradient-to-b from-black/30 to-black/60 group-hover:from-black/10 transition-all"></div>
              <div className="absolute bottom-0 left-0 p-6 text-white">
                <div className="font-serif text-xl mb-1">{project.name}</div>
                <div className="text-xs text-white/70 tracking-widest">{project.type}</div>
                <div className="text-[#6366F1] text-sm mt-3 group-hover:underline">View Site →</div>
              </div>
            </a>
          ))}
        </div>
      </section>

      {/* Contact Form */}
      <section id="contact" className="bg-[#1E3A5F] text-white py-20">
        <div className="max-w-xl mx-auto px-6">
          <div className="text-center mb-10">
            <h2 className="font-serif text-5xl mb-2">Let's Talk</h2>
            <p className="text-[#A5B4C8]">I'd Love to Hear From You</p>
          </div>
          <ContactForm />
        </div>
      </section>

      {/* About */}
      <section id="about" className="max-w-5xl mx-auto px-6 py-20 grid md:grid-cols-2 gap-12 items-center">
        <div>
          <h2 className="font-serif text-4xl mb-8">Get to Know Me</h2>
          <div className="prose prose-lg text-[#475569]">
            <p>Having spent my educational years in the classical liberal arts at schools such as Wyoming Catholic College, and my early career in Marketing and Technology with a Catholic publishing company, it has become my mission to help present the good purposes of your company or institution in a beautifully simple manner.</p>
            <p className="mt-6">How can I assist in building websites and company platforms that enable you to better pursue the mission you have set out upon?</p>
          </div>
        </div>
        <div className="bg-[#EEF2FF] aspect-[4/3] rounded-2xl"></div>
      </section>

      {/* Footer */}
      <footer className="border-t py-12 text-sm text-[#475569]">
        <div className="max-w-6xl mx-auto px-6 flex flex-col md:flex-row justify-between gap-4">
          <div>Merimee Digital Solutions</div>
          <div>merimeesoftware@gmail.com • Tel. 440-876-8036</div>
          <div className="flex gap-4">
            <a href="https://www.linkedin.com/in/michael-merimee/" target="_blank">LinkedIn</a>
            <a href="https://github.com/MtMerimee" target="_blank">GitHub</a>
            <a href="https://twitter.com/MichaelMerimee" target="_blank">X</a>
          </div>
          <div>© 2024, Merimee Digital Solutions. All rights reserved.</div>
        </div>
      </footer>
    </div>
  );
}
