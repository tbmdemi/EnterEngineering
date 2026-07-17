// Feature modules export: export const route = { path, label, Component }
import { route as complianceRoute } from "./features/compliance";
import { route as documentationAiRoute } from "./features/documentation-ai";
import { route as encounterRoute } from "./features/encounter";
import { route as preTreatmentRoute } from "./features/pre-treatment";
import { route as postTreatmentChatRoute } from "./features/post-treatment-chat";

export const featureRoutes = [encounterRoute, documentationAiRoute, preTreatmentRoute, postTreatmentChatRoute, complianceRoute];
