import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { RouterProvider } from "react-router";
import { ApiError } from "../api/http";
import { ToastProvider } from "../components/Toast/Toast";
import { toast } from "../components/Toast/toast-bus";
import { AuthProvider } from "./providers/AuthProvider";
import { ME_QUERY_KEY } from "./providers/auth-context";
import { ConfigProvider } from "./providers/ConfigProvider";
import { router } from "./router";

const queryClient: QueryClient = new QueryClient({
  queryCache: new QueryCache({
    // Global 401 on any guarded query: drop the session state — RequireAuth
    // then redirects to /login. The me query handles its own 401 (→ null).
    onError: (error, query) => {
      if (error instanceof ApiError && error.status === 401 && query.queryKey[0] !== "me") {
        queryClient.setQueryData(ME_QUERY_KEY, null);
        toast("Your session has expired. Please sign in again.");
      }
    },
  }),
  mutationCache: new MutationCache({
    // Same for mutations (R-2-wizard — every Continue is a PATCH/PUT). The
    // me-exists guard keeps failed LOGIN attempts (401s with no session) from
    // toasting "session expired".
    onError: (error) => {
      if (
        error instanceof ApiError &&
        error.status === 401 &&
        queryClient.getQueryData(ME_QUERY_KEY)
      ) {
        queryClient.setQueryData(ME_QUERY_KEY, null);
        toast("Your session has expired. Please sign in again.");
      }
    },
  }),
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider>
        <AuthProvider>
          <ToastProvider>
            <RouterProvider router={router} />
          </ToastProvider>
        </AuthProvider>
      </ConfigProvider>
    </QueryClientProvider>
  );
}
