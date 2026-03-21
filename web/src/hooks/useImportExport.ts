import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteImportJob,
  fetchImportJob,
  fetchImportJobs,
  importFile,
} from "../api/importExport";
import type { ImportOptions } from "../api/importExport";
import { queryKeys } from "../api/queryKeys";

export function useImportFile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, options }: { file: File; options: ImportOptions }) =>
      importFile(file, options),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.importExport.all });
    },
  });
}

export function useImportJob(id: number | null) {
  return useQuery({
    queryKey: queryKeys.importExport.job(id ?? 0),
    queryFn: () => fetchImportJob(id!),
    enabled: id != null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "processing" ? 2000 : false;
    },
  });
}

export function useImportJobs() {
  return useQuery({
    queryKey: queryKeys.importExport.jobs(),
    queryFn: fetchImportJobs,
  });
}

export function useDeleteImportJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteImportJob(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.importExport.all });
    },
  });
}
