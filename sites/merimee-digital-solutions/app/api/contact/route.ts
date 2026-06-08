import { NextResponse } from 'next/server';
import { z } from 'zod';

const contactSchema = z.object({
  name: z.string().min(2).max(120),
  email: z.string().email().max(200),
  organization: z.string().max(200).optional(),
  message: z.string().min(10).max(4000),
});

export const runtime = 'edge';

export async function POST(request: Request): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  const parsed = contactSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: 'Invalid form data', issues: parsed.error.flatten() },
      { status: 422 }
    );
  }

  try {
    const binding = (process.env as Record<string, string | undefined>).CONTACT_DB;
    if (binding) {
      // Cloudflare D1 binding path (production)
      await fetch(binding, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(parsed.data),
      });
    }

    const resendKey = process.env.RESEND_API_KEY;
    if (resendKey) {
      await fetch('https://api.resend.com/emails', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${resendKey}`,
        },
        body: JSON.stringify({
          from: 'website@merimeesolutions.com',
          to: 'michael@merimeesolutions.com',
          subject: `New inquiry from ${parsed.data.name}`,
          text: `Name: ${parsed.data.name}\nEmail: ${parsed.data.email}\nOrg: ${parsed.data.organization ?? '-'}\n\n${parsed.data.message}`,
        }),
      });
    }

    return NextResponse.json({ ok: true });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
