import { Navigate, useLocation, useParams, type Params } from 'react-router';

/** An address from before D-120: sent on to its new place, keeping the query string, so
 *  bookmarks and links in old bench logs still work. */
export function Moved({ to }: { to: (params: Params, query: URLSearchParams) => string }) {
  const params = useParams();
  const { search } = useLocation();
  return <Navigate replace to={to(params, new URLSearchParams(search))} />;
}

