export type ClinicKnowledgeScope = "clinic" | "service" | "laser_device";

export type ClinicKnowledgeEntry = {
  id: string;
  scope_type: ClinicKnowledgeScope;
  service_id: string | null;
  service_name: string | null;
  device_key: string | null;
  device_name: string | null;
  title: string;
  content: string;
  sort_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type ClinicKnowledgeBaseSnapshot = {
  entries: ClinicKnowledgeEntry[];
};

export type ClinicKnowledgeEntryInput = Omit<
  ClinicKnowledgeEntry,
  "id" | "service_name" | "device_name" | "created_at" | "updated_at"
>;

export type ClinicKnowledgeText = {
  content: string;
};
