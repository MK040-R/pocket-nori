import { getMeetingCategoryMeta, type MeetingCategory } from "@/lib/meeting-categories";

type MeetingCategoryBadgeProps = {
  category: MeetingCategory | null | undefined;
  className?: string;
};

export function MeetingCategoryBadge({
  category,
  className,
}: MeetingCategoryBadgeProps) {
  if (!category) {
    return null;
  }

  const meta = getMeetingCategoryMeta(category);

  return (
    <span
      className={[
        "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium",
        meta.badgeClassName,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {meta.shortLabel}
    </span>
  );
}
