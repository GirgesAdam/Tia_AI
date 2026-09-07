"use client";

import { useCallback, useEffect, useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Facebook, LoaderCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { completeWhatsAppEmbeddedSignupAction } from "./actions";

export type EmbeddedSignupConfig = {
  available: boolean;
  app_id: string | null;
  config_id: string | null;
  graph_api_version: string | null;
};

type SignupSession = {
  waba_id: string;
  phone_number_id: string;
  business_id?: string | null;
};

type FacebookLoginResponse = {
  authResponse?: { code?: string } | null;
  status?: string;
};

type FacebookSDK = {
  init: (options: {
    appId: string;
    cookie: boolean;
    xfbml: boolean;
    version: string;
  }) => void;
  login: (
    callback: (response: FacebookLoginResponse) => void,
    options: Record<string, unknown>,
  ) => void;
};

declare global {
  interface Window {
    FB?: FacebookSDK;
    fbAsyncInit?: () => void;
  }
}

const FACEBOOK_ORIGINS = new Set([
  "https://www.facebook.com",
  "https://web.facebook.com",
  "https://business.facebook.com",
]);

function parseSessionMessage(value: unknown): SignupSession | null {
  let payload = value;
  if (typeof value === "string") {
    try {
      payload = JSON.parse(value);
    } catch {
      return null;
    }
  }
  if (!payload || typeof payload !== "object") return null;
  const data = payload as {
    type?: unknown;
    event?: unknown;
    data?: { waba_id?: unknown; phone_number_id?: unknown; business_id?: unknown };
  };
  if (data.type !== "WA_EMBEDDED_SIGNUP" || data.event !== "FINISH") return null;
  const wabaId = typeof data.data?.waba_id === "string" ? data.data.waba_id : "";
  const phoneNumberId =
    typeof data.data?.phone_number_id === "string" ? data.data.phone_number_id : "";
  if (!wabaId || !phoneNumberId) return null;
  return {
    waba_id: wabaId,
    phone_number_id: phoneNumberId,
    business_id:
      typeof data.data?.business_id === "string" ? data.data.business_id : null,
  };
}

export function MetaEmbeddedSignup({ config }: { config: EmbeddedSignupConfig }) {
  const router = useRouter();
  const [sdkReady, setSdkReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const codeRef = useRef<string | null>(null);
  const sessionRef = useRef<SignupSession | null>(null);
  const submittingRef = useRef(false);

  const submitIfReady = useCallback(() => {
    const code = codeRef.current;
    const session = sessionRef.current;
    if (!code || !session || submittingRef.current) return;
    submittingRef.current = true;
    setError(null);
    startTransition(() => {
      void completeWhatsAppEmbeddedSignupAction({ code, ...session })
        .then(() => router.refresh())
        .catch((caught: unknown) => {
          setError(
            caught instanceof Error
              ? caught.message
              : "تعذر إكمال ربط واتساب. حاول مرة أخرى.",
          );
          submittingRef.current = false;
        });
    });
  }, [router]);

  useEffect(() => {
    if (!config.available || !config.app_id || !config.graph_api_version) return;

    const initialize = () => {
      if (!window.FB || !config.app_id || !config.graph_api_version) return;
      window.FB.init({
        appId: config.app_id,
        cookie: true,
        xfbml: false,
        version: config.graph_api_version,
      });
      setSdkReady(true);
    };

    if (window.FB) {
      initialize();
    } else {
      window.fbAsyncInit = initialize;
      if (!document.getElementById("facebook-jssdk")) {
        const script = document.createElement("script");
        script.id = "facebook-jssdk";
        script.async = true;
        script.defer = true;
        script.crossOrigin = "anonymous";
        script.src = "https://connect.facebook.net/en_US/sdk.js";
        script.onerror = () => setError("تعذر تحميل شاشة Meta. جرّب مرة أخرى.");
        document.body.appendChild(script);
      }
    }

    const onMessage = (event: MessageEvent) => {
      if (!FACEBOOK_ORIGINS.has(event.origin)) return;
      const session = parseSessionMessage(event.data);
      if (!session) return;
      sessionRef.current = session;
      submitIfReady();
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [config.app_id, config.available, config.graph_api_version, submitIfReady]);

  function launch() {
    setError(null);
    codeRef.current = null;
    sessionRef.current = null;
    submittingRef.current = false;
    if (!window.FB || !config.config_id) {
      setError("شاشة Meta لسه ماجهزتش. حاول تاني بعد ثواني.");
      return;
    }
    window.FB.login(
      (response) => {
        const code = response.authResponse?.code?.trim();
        if (!code) {
          setError("الربط لم يكتمل في Meta. لم يتم تغيير أي إعداد في Tia.");
          return;
        }
        codeRef.current = code;
        submitIfReady();
      },
      {
        config_id: config.config_id,
        response_type: "code",
        override_default_response_type: true,
        extras: {
          feature: "whatsapp_embedded_signup",
          sessionInfoVersion: "3",
        },
      },
    );
  }

  if (!config.available) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-900">
        الربط المباشر مع Meta غير مفعّل على منصة Tia حاليًا. دي خطوة إعداد على Tia نفسها، مش مطلوب من العيادة نسخ IDs أو Tokens يدويًا.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <Button type="button" onClick={launch} disabled={!sdkReady || isPending}>
        {isPending ? <LoaderCircle size={16} className="animate-spin" /> : <Facebook size={16} />}
        {isPending ? "جاري إكمال الربط..." : "ربط واتساب مع Meta"}
      </Button>
      <p className="text-xs leading-5 text-[var(--muted)]">
        هتفتح شاشة Meta الرسمية. اختار Business العيادة ورقم واتساب فقط؛ Tia تستلم بيانات الربط تقنيًا بدون ما تظهر لك Tokens.
      </p>
      {error && <p className="text-sm text-rose-700">{error}</p>}
    </div>
  );
}
