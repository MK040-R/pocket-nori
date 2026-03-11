"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { getBrief, type BriefDetail } from "@/lib/api";

export default function BriefDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [brief, setBrief] = useState<BriefDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getBrief(id);
        if (mounted) {
          setBrief(data);
        }
      } catch (loadError) {
        if (mounted) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load brief");
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };

    void load();
    return () => {
      mounted = false;
    };
  }, [id]);

  if (loading) {
    return <section className="card p-4 text-sm text-ink-secondary">Loading brief...</section>;
  }

  if (error || !brief) {
    return (
      <section className="card border border-emphasis bg-accent-subtle p-4 text-sm text-accent">
        {error ?? "Brief not found"}
      </section>
    );
  }

  return (
    <div className="space-y-4">
      <section className="card p-6">
        <h1 className="text-2xl font-semibold">Pre-meeting brief</h1>
        <p className="mt-2 text-sm text-ink-tertiary">
          Generated {new Date(brief.generated_at).toLocaleString()}
        </p>
        <p className="mt-4 whitespace-pre-wrap text-sm leading-relaxed text-ink-primary">{brief.content}</p>
      </section>

      <section className="card p-5">
        <h2 className="text-lg font-semibold">Citations</h2>
        <div className="mt-3 space-y-2">
          {brief.citations.length === 0 && (
            <p className="text-sm text-ink-tertiary">No citation segments linked yet.</p>
          )}
          {brief.citations.map((citation) => (
            <article key={citation.segment_id} className="rounded border border-soft p-3">
              <p className="mono text-xs text-ink-tertiary">
                {citation.speaker_id} · {citation.start_ms}ms
              </p>
              <p className="mono mt-1 text-sm text-ink-secondary">{citation.text}</p>
              <Link
                href={`/meetings/${citation.conversation_id}`}
                className="mt-2 inline-block text-xs text-accent hover:text-accent-hover"
              >
                Open source meeting
              </Link>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
