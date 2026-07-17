// Feature modules export: export const route = { path, label, Component }
import { route as complianceRoute } from "./features/compliance";
import { route as encounterRoute } from "./features/encounter";

export const featureRoutes = [encounterRoute, complianceRoute];
