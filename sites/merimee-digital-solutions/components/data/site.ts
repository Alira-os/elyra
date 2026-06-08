export type NavLink = {
  label: string;
  href: string;
  isCta?: boolean;
  children?: NavLink[];
};

export const navLinks: NavLink[] = [
  { label: "Home", href: "#top" },
  {
    label: "Services",
    href: "#services",
    children: [
      { label: "Web Design", href: "#services" },
      { label: "Mobile Apps", href: "#services" },
      { label: "Brand Messaging", href: "#services" },
      { label: "Build Interest", href: "#services" },
    ],
  },
  { label: "Portfolio", href: "#portfolio" },
  { label: "About", href: "#about" },
  { label: "Contact", href: "#contact" },
  { label: "Let's Talk", href: "#contact", isCta: true },
];

export const services = [
  {
    title: "Web Design",
    href: "#services",
    icon: "web",
    description:
      "Beautiful, mission-aligned websites that read clearly and convert with grace.",
  },
  {
    title: "Mobile Apps",
    href: "#services",
    icon: "apps",
    description:
      "Native and cross-platform apps designed to put your work in your audience's pocket.",
  },
  {
    title: "Brand Messaging",
    href: "#services",
    icon: "brand",
    description:
      "Clarify your cause with copy and positioning that earns attention and trust.",
  },
  {
    title: "Build Interest",
    href: "#services",
    icon: "growth",
    description:
      "Thoughtful campaigns that introduce your work to the people who need it most.",
  },
];

export const processSteps = [
  {
    title: "Schedule a Call",
    body: "Reach out and discover how we might work together and find a solution.",
  },
  {
    title: "Craft a Plan",
    body: "Let's put together an effective plan for realizing your goals and creating something beautiful.",
  },
  {
    title: "Realize Your Vision",
    body: "Don't resign yourself to mediocrity. Let's be great together.",
  },
];

export type Project = {
  title: string;
  href: string;
  tags: string[];
  thumbnail: string;
};

export const projects: Project[] = [
  {
    title: "Holy Rollers",
    href: "https://www.holyrollers.us/",
    tags: ["Website Design", "Messaging"],
    thumbnail: "/images/projects/holy-rollers.jpg",
  },
  {
    title: "Chesterton Academy of Akron",
    href: "https://akronchestertonacademy.org/",
    tags: ["Web Redesign", "Building Interest"],
    thumbnail: "/images/projects/chesterton.jpg",
  },
  {
    title: "Parker Eidle",
    href: "https://www.parkereidle.com/",
    tags: ["Website Design"],
    thumbnail: "/images/projects/parker-eidle.jpg",
  },
  {
    title: "Alena Carter",
    href: "http://www.alenacarter.art",
    tags: ["Website Design", "Messaging"],
    thumbnail: "/images/projects/alena-carter.jpg",
  },
  {
    title: "Bonfire Media",
    href: "https://www.bonfiremedia.art/",
    tags: ["Website Design", "Messaging", "Building Interest"],
    thumbnail: "/images/projects/bonfire.jpg",
  },
];

export const contactMeta = {
  headline: "Let's Talk",
  subheadline: "I'd Love to Hear From You",
};

export type ContactField = {
  name: string;
  label: string;
  type: "text" | "email" | "tel";
  required: boolean;
  placeholder?: string;
};

export const contactFields: ContactField[] = [
  { name: "firstName", label: "First name", type: "text", required: true },
  { name: "lastName", label: "Last name", type: "text", required: true },
  {
    name: "company",
    label: "Company name (optional)",
    type: "text",
    required: false,
    placeholder: "Company name",
  },
  {
    name: "projectType",
    label: "What would you like to talk about?",
    type: "text",
    required: false,
    placeholder: "My website, an app idea, connecting with people, etc…",
  },
  { name: "email", label: "Email", type: "email", required: true },
  {
    name: "phone",
    label: "Phone (optional)",
    type: "tel",
    required: false,
    placeholder: "Phone",
  },
];

export const aboutContent = {
  portrait: {
    src: "/images/portrait.jpg",
    alt: "Michael Merimee, founder of Merimee Digital Solutions",
  },
  body: "Having spent my educational years in the classical liberal arts at schools such as Wyoming Catholic College, and my early career in Marketing and Technology with a Catholic publishing company, it has become my mission to help present the good purposes of your company or institution in a beautifully simple manner. How can I assist in building websites and company platforms that enable you to better pursue the mission you have set out upon?",
};

export const contactInfo = {
  email: "merimeesoftware@gmail.com",
  phone: "440-876-8036",
};

export const socialLinks = [
  {
    platform: "linkedin" as const,
    href: "https://www.linkedin.com/in/michael-merimee/",
    label: "LinkedIn",
  },
  {
    platform: "github" as const,
    href: "https://github.com/MtMerimee",
    label: "GitHub",
  },
  {
    platform: "twitter" as const,
    href: "https://twitter.com/MichaelMerimee",
    label: "X",
  },
];

export const footerCopy = "©2024, Merimee Digital Solutions, All rights reserved.";
