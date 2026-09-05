import { createClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

// null when the NEXT_PUBLIC_SUPABASE_* vars are unset: the app then runs on offline identities only.
export const supabase = url && key ? createClient(url, key) : null;
