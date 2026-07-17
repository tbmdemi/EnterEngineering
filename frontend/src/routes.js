// Feature modules export: export const route = { path, label, Component }
import { route as complianceRoute } from "./features/compliance";
import { route as documentationAiRoute } from "./features/documentation-ai";
import { route as encounterRoute } from "./features/encounter";

export const featureRoutes = [encounterRoute, documentationAiRoute, complianceRoute];
