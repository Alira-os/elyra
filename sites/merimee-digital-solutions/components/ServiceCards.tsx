import Image from 'next/image';
import { SERVICES } from '@/lib/content';
import { Card } from './ui/Card';

export function ServiceCards() {
  return (
    <section
      id="services"
      className="section bg-surface"
      aria-labelledby="services-heading"
    >
      <div className="container">
        <div className="text-center max-w-2xl mx-auto mb-12">
          <p className="eyebrow">Services</p>
          <h2 id="services-heading" className="text-pretty">
            How Can I Help You?
          </h2>
        </div>

        <ul
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6"
          role="list"
        >
          {SERVICES.map((service) => (
            <li key={service.id} className="h-full">
              <Card
                variant="elevated"
                className="h-full flex flex-col items-center text-center gap-4"
              >
                <div className="w-20 h-20 relative flex items-center justify-center">
                  <Image
                    src={service.icon}
                    alt={service.alt}
                    width={80}
                    height={80}
                    className="w-full h-full object-contain"
                    loading="lazy"
                  />
                </div>
                <h3 className="text-xl">{service.title}</h3>
                <p className="text-muted text-sm leading-relaxed">
                  {service.description}
                </p>
              </Card>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
