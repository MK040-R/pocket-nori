export const MEETING_CATEGORY_VALUES = [
  "strategy",
  "client",
  "1on1",
  "agency",
  "partner",
  "team",
  "other",
] as const;

export type MeetingCategory = (typeof MEETING_CATEGORY_VALUES)[number];

type MeetingCategoryMeta = {
  value: MeetingCategory;
  label: string;
  shortLabel: string;
  badgeClassName: string;
};

export const MEETING_CATEGORY_OPTIONS: MeetingCategoryMeta[] = [
  {
    value: "strategy",
    label: "Strategy",
    shortLabel: "Strategy",
    badgeClassName: "border-[#c9d5f5] bg-[#edf2ff] text-[#36559b]",
  },
  {
    value: "client",
    label: "Client",
    shortLabel: "Client",
    badgeClassName: "border-[#b9e7d4] bg-[#ecfbf5] text-[#0f7d59]",
  },
  {
    value: "1on1",
    label: "1:1",
    shortLabel: "1:1",
    badgeClassName: "border-[#f2d3ab] bg-[#fff6ea] text-[#a55c16]",
  },
  {
    value: "agency",
    label: "Agency",
    shortLabel: "Agency",
    badgeClassName: "border-[#d6ddef] bg-[#f4f7fd] text-[#4f628f]",
  },
  {
    value: "partner",
    label: "Partner",
    shortLabel: "Partner",
    badgeClassName: "border-[#bfddec] bg-[#edf8ff] text-[#1d6987]",
  },
  {
    value: "team",
    label: "Team",
    shortLabel: "Team",
    badgeClassName: "border-[#c8e7d2] bg-[#f2fbf5] text-[#216f4d]",
  },
  {
    value: "other",
    label: "Other",
    shortLabel: "Other",
    badgeClassName: "border-[#d5dde6] bg-[#f7fafc] text-[#536170]",
  },
] satisfies MeetingCategoryMeta[];

const categoryMetaByValue = MEETING_CATEGORY_OPTIONS.reduce<Record<MeetingCategory, MeetingCategoryMeta>>(
  (accumulator, option) => {
    accumulator[option.value] = option;
    return accumulator;
  },
  {} as Record<MeetingCategory, MeetingCategoryMeta>,
);

export function isMeetingCategory(value: string | null | undefined): value is MeetingCategory {
  if (!value) {
    return false;
  }
  return MEETING_CATEGORY_VALUES.includes(value as MeetingCategory);
}

export function getMeetingCategoryMeta(category: MeetingCategory): MeetingCategoryMeta {
  return categoryMetaByValue[category];
}

export function formatMeetingCategoryLabel(category: MeetingCategory | null | undefined): string {
  if (!category || !isMeetingCategory(category)) {
    return "Uncategorized";
  }
  return categoryMetaByValue[category].label;
}
