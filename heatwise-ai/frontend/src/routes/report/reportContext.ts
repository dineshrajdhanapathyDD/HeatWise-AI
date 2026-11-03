import { useOutletContext } from "react-router-dom";

import type { AssessmentRecord } from "../../api/types";

export interface ReportOutlet {
  record: AssessmentRecord;
}

export function useReportRecord(): AssessmentRecord {
  return useOutletContext<ReportOutlet>().record;
}
