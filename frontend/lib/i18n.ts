"use client";

import { useCallback, useEffect, useState } from "react";

export type Locale = "ja" | "en";

const dict = {
  // ── App-wide ──
  "app.title": { ja: "医療クローラー", en: "Health Care Crawler" },
  "app.subtitle": { ja: "医療求人データ自動収集システム", en: "Automated Healthcare Job Data Collection" },
  "app.description": { ja: "医療・介護業界の求人情報を自動収集し、Google Sheetsに整理して出力します。", en: "Automatically collect healthcare job listings and organize them into Google Sheets." },

  // ── Nav ──
  "nav.dashboard": { ja: "ダッシュボード", en: "Dashboard" },
  "nav.config": { ja: "設定", en: "Settings" },
  "nav.logs": { ja: "実行ログ", en: "Run Logs" },
  "nav.users": { ja: "ユーザー", en: "Users" },
  "nav.logout": { ja: "ログアウト", en: "Log out" },

  // ── Landing ──
  "landing.hero": { ja: "医療求人データを\n自動収集", en: "Automated\nHealthcare Job Collection" },
  "landing.heroSub": { ja: "11サイトから求人情報を収集し、個人情報をマスキングしてGoogle Sheetsへ出力", en: "Scrape job data from 11 sites, mask sensitive info, and output to Google Sheets" },
  "landing.cta.start": { ja: "始める", en: "Get Started" },
  "landing.cta.login": { ja: "ログイン", en: "Sign In" },
  "landing.feature1.title": { ja: "自動スクレイピング", en: "Auto Scraping" },
  "landing.feature1.desc": { ja: "11の医療求人サイトから毎日自動収集", en: "Daily auto-collection from 11 healthcare job sites" },
  "landing.feature2.title": { ja: "個人情報マスキング", en: "Data Masking" },
  "landing.feature2.desc": { ja: "施設名・連絡先を自動でマスキング処理", en: "Automatically mask facility names & contact info" },
  "landing.feature3.title": { ja: "Google Sheets連携", en: "Sheets Integration" },
  "landing.feature3.desc": { ja: "あなたのGoogle Driveに直接出力", en: "Output directly to your Google Drive" },

  // ── Login ──
  "login.title": { ja: "ログイン", en: "Sign In" },
  "login.email": { ja: "メールアドレス", en: "Email address" },
  "login.password": { ja: "パスワード", en: "Password" },
  "login.submit": { ja: "ログイン", en: "Sign In" },
  "login.noAccount": { ja: "アカウントをお持ちでない方", en: "Don't have an account?" },
  "login.startOnboarding": { ja: "新規登録はこちら", en: "Start onboarding" },
  "login.error": { ja: "ログインに失敗しました", en: "Login failed" },

  // ── Onboarding ──
  "onboarding.title": { ja: "セルフサーブ オンボーディング", en: "Self-Serve Onboarding" },
  "onboarding.step1": { ja: "アカウント作成", en: "Create Account" },
  "onboarding.step2": { ja: "Google接続", en: "Connect Google" },
  "onboarding.step3": { ja: "セットアップ中", en: "Setting Up" },
  "onboarding.step4": { ja: "完了", en: "Ready" },
  "onboarding.company": { ja: "会社名", en: "Company name" },
  "onboarding.name": { ja: "お名前", en: "Your name" },
  "onboarding.email": { ja: "メールアドレス", en: "Email" },
  "onboarding.password": { ja: "パスワード", en: "Password" },
  "onboarding.continue": { ja: "次へ", en: "Continue" },
  "onboarding.google.title": { ja: "Googleアカウント接続", en: "Connect Google Account" },
  "onboarding.google.bullet1": { ja: "Google Driveにスプレッドシートを作成（あなたが所有）", en: "Spreadsheet created in your Google Drive — you own it" },
  "onboarding.google.bullet2": { ja: "マスキング済みデータのみ保存", en: "Masked data only — facility names redacted before saving" },
  "onboarding.google.bullet3": { ja: "毎日午前6時（JST）に自動更新", en: "Auto-updates daily at 6 AM JST" },
  "onboarding.google.connect": { ja: "Googleで続ける", en: "Continue with Google" },
  "onboarding.progress.0": { ja: "Googleアカウント接続完了", en: "Google account connected" },
  "onboarding.progress.1": { ja: "Google Sheetsを作成中…", en: "Creating your Google Sheet…" },
  "onboarding.progress.2": { ja: "「Jobs Masked」タブをセットアップ中", en: "Setting up Jobs Masked tab" },
  "onboarding.progress.3": { ja: "「Jobs Raw」タブをセットアップ中", en: "Setting up Jobs Raw tab" },
  "onboarding.progress.4": { ja: "11サイトのスクレイパーを設定中", en: "Configuring scraper for 11 sites" },
  "onboarding.done.title": { ja: "準備完了！", en: "You're all set!" },
  "onboarding.done.goToDashboard": { ja: "ダッシュボードへ →", en: "Go to dashboard →" },
  "onboarding.done.dataNote": { ja: "データはあなたのGoogle Driveに保存されます", en: "Your data stays in your Google Drive" },
  "onboarding.error.register": { ja: "登録に失敗しました", en: "Failed to register" },
  "onboarding.error.google": { ja: "Google接続に失敗しました", en: "Google connect failed" },

  // ── Dashboard ──
  "dashboard.title": { ja: "ダッシュボード", en: "Dashboard" },
  "dashboard.sheetsStatus": { ja: "Google Sheets ステータス", en: "Google Sheets Status" },
  "dashboard.connected": { ja: "接続済み", en: "Connected" },
  "dashboard.notConnected": { ja: "未接続", en: "Not connected" },
  "dashboard.notConnectedMsg": { ja: "Google Sheetsが接続されていません — 設定から接続してください", en: "Google Sheets not connected — go to Settings to connect" },
  "dashboard.lastRun": { ja: "最終実行", en: "Last Run" },
  "dashboard.never": { ja: "未実行", en: "Never" },
  "dashboard.runNow": { ja: "今すぐ実行", en: "Run Now" },
  "dashboard.viewSheet": { ja: "シートを表示", en: "View Sheet" },
  "dashboard.running": { ja: "実行中…", en: "Running…" },
  "dashboard.sites": { ja: "サイト一覧", en: "Sites" },
  "dashboard.addSite": { ja: "カスタムサイトを追加", en: "Add Custom Site" },
  "dashboard.siteStatus.success": { ja: "✅ 正常", en: "✅ Working" },
  "dashboard.siteStatus.failed": { ja: "⚠️ エラー", en: "⚠️ Broken" },
  "dashboard.siteStatus.unknown": { ja: "— 未実行", en: "— Unknown" },
  "dashboard.runSummary": { ja: "実行結果", en: "Run Summary" },
  "dashboard.jobsFound": { ja: "求人数", en: "Jobs found" },
  "dashboard.sheetsNotice": { ja: "データが Google Sheet に書き込まれました", en: "Data written to your Google Sheet" },
  "dashboard.rawTab": { ja: "raw_data タブ：", en: "raw_data tab:" },
  "dashboard.maskedTab": { ja: "masked_data タブ：", en: "masked_data tab:" },
  "dashboard.unmasked": { ja: "未マスク", en: "unmasked" },
  "dashboard.masked": { ja: "マスク済み", en: "masked" },
  "dashboard.pollFailed": { ja: "実行に失敗しました", en: "Run failed" },

  // ── Config ──
  "config.title": { ja: "設定", en: "Settings" },
  "config.sheetsConnection": { ja: "Google Sheets 接続", en: "Google Sheets Connection" },
  "config.connectedAs": { ja: "として接続中", en: "Connected as" },
  "config.disconnect": { ja: "接続解除", en: "Disconnect" },
  "config.connect": { ja: "Googleアカウントを接続", en: "Connect Google Account" },
  "config.testConnection": { ja: "接続テスト", en: "Test Connection" },
  "config.notConnected": { ja: "未接続", en: "Not connected" },

  // ── Logs ──
  "logs.title": { ja: "実行ログ", en: "Run Logs" },
  "logs.date": { ja: "日時", en: "Date" },
  "logs.trigger": { ja: "トリガー", en: "Trigger" },
  "logs.sites": { ja: "サイト数", en: "Sites" },
  "logs.listings": { ja: "求人数", en: "Listings" },
  "logs.status": { ja: "ステータス", en: "Status" },
  "logs.errors": { ja: "エラー", en: "Errors" },
  "logs.sheetUrl": { ja: "シートURL", en: "Sheet URL" },
  "logs.empty": { ja: "実行ログはまだありません", en: "No run logs yet" },
  "logs.success": { ja: "成功", en: "Success" },
  "logs.failed": { ja: "失敗", en: "Failed" },

  // ── Users ──
  "users.title": { ja: "ユーザー管理", en: "User Management" },
  "users.empty": { ja: "ユーザー管理機能は近日公開予定です", en: "User management coming soon" },

  // ── Common ──
  "common.loading": { ja: "読み込み中…", en: "Loading…" },
  "common.error": { ja: "エラーが発生しました", en: "An error occurred" },
  "common.sheet": { ja: "シート", en: "Sheet" },
} as const;

export type TranslationKey = keyof typeof dict;

export function translate(key: TranslationKey, locale: Locale): string {
  return dict[key]?.[locale] ?? key;
}

export function useLocale() {
  const [locale, setLocaleState] = useState<Locale>("ja");

  useEffect(() => {
    const stored = localStorage.getItem("locale") as Locale | null;
    if (stored === "ja" || stored === "en") {
      setLocaleState(stored);
    }
  }, []);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    localStorage.setItem("locale", l);
  }, []);

  const t = useCallback(
    (key: TranslationKey) => translate(key, locale),
    [locale],
  );

  return { locale, setLocale, t };
}
