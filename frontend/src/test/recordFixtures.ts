// The design refactor (26 November 2026): what the five reads of Evidence answer. Every value here was read from the
// backend after one real demo walk (import, I own this system, Verify, two tests added, Run all, then a retest on
// acme-sign 1.4.3), so the words are the backend's own. The one download in `evidenceFilesWithOne` is written in the
// record's form: that walk had downloaded nothing.
import type { DecisionsView, EvidenceFilesView, HistoryView, TimelineEntryDetail, TimelineView } from "../api";

export const timelineView: TimelineView = {
  plan_id: 1,
  is_demo: true,
  title: "Timeline",
  subline:
    "Everything that happened in this assessment, newest first: every run and what it found, every decision with who made it, every change to a system, and every file in and out. Reading it runs nothing.",
  chosen: {
    area: "all",
    kind: "all",
    q: "",
  },
  areas: [
    {
      key: "all",
      label: "All",
      count: 8,
    },
    {
      key: "observe",
      label: "Observatory and Verify",
      count: 2,
    },
    {
      key: "advisories",
      label: "Advisories",
      count: 0,
    },
    {
      key: "checks",
      label: "Checks",
      count: 4,
    },
    {
      key: "fixes",
      label: "Fixes",
      count: 0,
    },
    {
      key: "migration",
      label: "Migration plan",
      count: 0,
    },
    {
      key: "dependencies",
      label: "Dependencies",
      count: 0,
    },
    {
      key: "watch",
      label: "Change watch",
      count: 0,
    },
    {
      key: "assessment",
      label: "The assessment",
      count: 2,
    },
  ],
  kinds: [
    {
      key: "all",
      label: "Everything",
      count: 8,
    },
    {
      key: "runs",
      label: "Runs and results",
      count: 3,
    },
    {
      key: "people",
      label: "What people did",
      count: 4,
    },
    {
      key: "system",
      label: "Changes to a system",
      count: 0,
    },
    {
      key: "files",
      label: "Files in and out",
      count: 1,
    },
  ],
  total: 8,
  days: [
    {
      date: "2026-11-25",
      count: 8,
      entries: [
        {
          id: "retest-1",
          at: "2026-11-26T04:22:15.050Z",
          area: {
            key: "checks",
            label: "Checks",
          },
          kind: {
            key: "runs",
            label: "Runs and results",
          },
          icon: "flask",
          lead: "Retest on acme-sign 1.4.3:",
          rest: [
            {
              t: "text",
              v: " the 7 tests in the plan.",
            },
          ],
          who: {
            name: "You",
            source: "default",
            source_label: "No name was typed in Settings, so it reads “You”",
            demo: false,
            recorded: true,
            button: "Retest new version",
          },
          also: [],
          decided_by: "decided by the separate reviewer",
          marks: [],
          source_tags: [
            {
              key: "live",
              label: "Observed live",
              meaning:
                "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
              note: null,
            },
            {
              key: "lab",
              label: "Proven in the lab",
              meaning: "Run on a copy on this computer, never on your live system.",
              note: null,
            },
          ],
          runs: [
            {
              run_id: 8,
              verify_run_id: null,
              name: "Old TLS versions",
              ran_on: "localhost:46525",
              result: {
                label: "Failed",
                tone: "fail",
              },
              source_tag: {
                key: "live",
                label: "Observed live",
                meaning:
                  "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
                note: "Read from localhost:46525, an address in your file that you confirmed, with handshakes only.",
              },
              link: {
                page: "evidence",
                item: "retest-1-on-1",
              },
            },
            {
              run_id: 9,
              verify_run_id: null,
              name: "Certificate strength",
              ran_on: "localhost:46525",
              result: {
                label: "Passed",
                tone: "pass",
              },
              source_tag: {
                key: "live",
                label: "Observed live",
                meaning:
                  "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
                note: "Read from localhost:46525, an address in your file that you confirmed, with handshakes only.",
              },
              link: {
                page: "evidence",
                item: "retest-2-on-1",
              },
            },
            {
              run_id: 10,
              verify_run_id: null,
              name: "Attacker tricks (our short list)",
              ran_on: "acme-sign 1.4.3",
              result: {
                label: "Passed",
                tone: "pass",
              },
              source_tag: {
                key: "lab",
                label: "Proven in the lab",
                meaning: "Run on a copy on this computer, never on your live system.",
                note: "Run on a copy of acme-sign 1.4.3 on this computer. Your live system was not touched.",
              },
              link: {
                page: "evidence",
                item: "retest-4-on-1",
              },
            },
            {
              run_id: 11,
              verify_run_id: null,
              name: "Independent exam (Wycheproof)",
              ran_on: "acme-sign 1.4.3",
              result: {
                label: "Passed",
                tone: "pass",
              },
              source_tag: {
                key: "lab",
                label: "Proven in the lab",
                meaning: "Run on a copy on this computer, never on your live system.",
                note: "Run on a copy of acme-sign 1.4.3 on this computer. Your live system was not touched.",
              },
              link: {
                page: "evidence",
                item: "retest-3-on-1",
              },
            },
            {
              run_id: 12,
              verify_run_id: null,
              name: "Speed and size",
              ran_on: "acme-sign 1.4.3",
              result: {
                label: "No slowdown beyond measured noise",
                tone: "pass",
              },
              source_tag: {
                key: "lab",
                label: "Proven in the lab",
                meaning: "Run on a copy on this computer, never on your live system.",
                note: "Run on a copy of acme-sign 1.4.3 on this computer. Your live system was not touched.",
              },
              link: {
                page: "evidence",
                item: "retest-5-on-1",
              },
            },
            {
              run_id: 13,
              verify_run_id: null,
              name: "ML-DSA-65 comparison",
              ran_on: "acme-sign 1.4.3",
              result: {
                label: "Measured",
                tone: "neutral",
              },
              source_tag: {
                key: "lab",
                label: "Proven in the lab",
                meaning: "Run on a copy on this computer, never on your live system.",
                note: "Run on a copy of acme-sign 1.4.3 on this computer. Your live system was not touched.",
              },
              link: {
                page: "evidence",
                item: "retest-7-on-1",
              },
            },
            {
              run_id: 14,
              verify_run_id: null,
              name: "Post-quantum readiness",
              ran_on: "localhost:46525",
              result: {
                label: "Not offered",
                tone: "neutral",
              },
              source_tag: {
                key: "live",
                label: "Observed live",
                meaning:
                  "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
                note: "Read from localhost:46525, an address in your file that you confirmed, with handshakes only.",
              },
              link: {
                page: "evidence",
                item: "retest-6-on-1",
              },
            },
          ],
          counts: [
            {
              label: "Failed",
              tone: "fail",
              count: 1,
            },
            {
              label: "No slowdown beyond measured noise",
              tone: "pass",
              count: 1,
            },
            {
              label: "Passed",
              tone: "pass",
              count: 3,
            },
            {
              label: "Measured",
              tone: "neutral",
              count: 1,
            },
            {
              label: "Not offered",
              tone: "neutral",
              count: 1,
            },
          ],
          outcome: null,
          pending: 0,
          link: {
            page: "evidence",
            item: null,
          },
          apart: false,
        },
        {
          id: "press-6",
          at: "2026-11-26T04:21:51.032Z",
          area: {
            key: "checks",
            label: "Checks",
          },
          kind: {
            key: "runs",
            label: "Runs and results",
          },
          icon: "flask",
          lead: "Run all:",
          rest: [
            {
              t: "text",
              v: " the 7 tests in the plan.",
            },
          ],
          who: {
            name: "You",
            source: "default",
            source_label: "No name was typed in Settings, so it reads “You”",
            demo: false,
            recorded: true,
            button: "Run all",
          },
          also: [],
          decided_by: "decided by the separate reviewer",
          marks: [],
          source_tags: [
            {
              key: "live",
              label: "Observed live",
              meaning:
                "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
              note: null,
            },
            {
              key: "lab",
              label: "Proven in the lab",
              meaning: "Run on a copy on this computer, never on your live system.",
              note: null,
            },
          ],
          runs: [
            {
              run_id: 1,
              verify_run_id: null,
              name: "Old TLS versions",
              ran_on: "localhost:46525",
              result: {
                label: "Failed",
                tone: "fail",
              },
              source_tag: {
                key: "live",
                label: "Observed live",
                meaning:
                  "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
                note: "Read from localhost:46525, an address in your file that you confirmed, with handshakes only.",
              },
              link: {
                page: "evidence",
                item: "test-1",
              },
            },
            {
              run_id: 2,
              verify_run_id: null,
              name: "Certificate strength",
              ran_on: "localhost:46525",
              result: {
                label: "Passed",
                tone: "pass",
              },
              source_tag: {
                key: "live",
                label: "Observed live",
                meaning:
                  "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
                note: "Read from localhost:46525, an address in your file that you confirmed, with handshakes only.",
              },
              link: {
                page: "evidence",
                item: "test-2",
              },
            },
            {
              run_id: 3,
              verify_run_id: null,
              name: "Attacker tricks (our short list)",
              ran_on: "acme-sign 1.4.2",
              result: {
                label: "Failed",
                tone: "fail",
              },
              source_tag: {
                key: "lab",
                label: "Proven in the lab",
                meaning: "Run on a copy on this computer, never on your live system.",
                note: "Run on a copy of acme-sign 1.4.2 on this computer. Your live system was not touched.",
              },
              link: {
                page: "evidence",
                item: "test-4",
              },
            },
            {
              run_id: 4,
              verify_run_id: null,
              name: "Independent exam (Wycheproof)",
              ran_on: "acme-sign 1.4.2",
              result: {
                label: "Failed",
                tone: "fail",
              },
              source_tag: {
                key: "lab",
                label: "Proven in the lab",
                meaning: "Run on a copy on this computer, never on your live system.",
                note: "Run on a copy of acme-sign 1.4.2 on this computer. Your live system was not touched.",
              },
              link: {
                page: "evidence",
                item: "test-3",
              },
            },
            {
              run_id: 5,
              verify_run_id: null,
              name: "Speed and size",
              ran_on: "acme-sign 1.4.2",
              result: {
                label: "Measured",
                tone: "neutral",
              },
              source_tag: {
                key: "lab",
                label: "Proven in the lab",
                meaning: "Run on a copy on this computer, never on your live system.",
                note: "Run on a copy of acme-sign 1.4.2 on this computer. Your live system was not touched.",
              },
              link: {
                page: "evidence",
                item: "test-5",
              },
            },
            {
              run_id: 6,
              verify_run_id: null,
              name: "ML-DSA-65 comparison",
              ran_on: "acme-sign 1.4.2",
              result: {
                label: "Measured",
                tone: "neutral",
              },
              source_tag: {
                key: "lab",
                label: "Proven in the lab",
                meaning: "Run on a copy on this computer, never on your live system.",
                note: "Run on a copy of acme-sign 1.4.2 on this computer. Your live system was not touched.",
              },
              link: {
                page: "evidence",
                item: "test-7",
              },
            },
            {
              run_id: 7,
              verify_run_id: null,
              name: "Post-quantum readiness",
              ran_on: "localhost:46525",
              result: {
                label: "Not offered",
                tone: "neutral",
              },
              source_tag: {
                key: "live",
                label: "Observed live",
                meaning:
                  "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
                note: "Read from localhost:46525, an address in your file that you confirmed, with handshakes only.",
              },
              link: {
                page: "evidence",
                item: "test-6",
              },
            },
          ],
          counts: [
            {
              label: "Failed",
              tone: "fail",
              count: 3,
            },
            {
              label: "Passed",
              tone: "pass",
              count: 1,
            },
            {
              label: "Measured",
              tone: "neutral",
              count: 2,
            },
            {
              label: "Not offered",
              tone: "neutral",
              count: 1,
            },
          ],
          outcome: null,
          pending: 0,
          link: {
            page: "checks",
            item: null,
          },
          apart: false,
        },
        {
          id: "action-5",
          at: "2026-11-26T04:21:51.014Z",
          area: {
            key: "checks",
            label: "Checks",
          },
          kind: {
            key: "people",
            label: "What people did",
          },
          icon: "list",
          lead: "Added to the test plan:",
          rest: [
            {
              t: "text",
              v: " “ML-DSA-65 comparison”.",
            },
          ],
          who: {
            name: "You",
            source: "default",
            source_label: "No name was typed in Settings, so it reads “You”",
            demo: false,
            recorded: true,
            button: "Add test",
          },
          also: [],
          decided_by: null,
          marks: [],
          source_tags: [],
          runs: [],
          counts: [],
          outcome: null,
          pending: 0,
          link: {
            page: "checks",
            item: null,
          },
          apart: false,
        },
        {
          id: "action-4",
          at: "2026-11-26T04:21:50.990Z",
          area: {
            key: "checks",
            label: "Checks",
          },
          kind: {
            key: "people",
            label: "What people did",
          },
          icon: "list",
          lead: "Added to the test plan:",
          rest: [
            {
              t: "text",
              v: " “Post-quantum readiness”.",
            },
          ],
          who: {
            name: "You",
            source: "default",
            source_label: "No name was typed in Settings, so it reads “You”",
            demo: false,
            recorded: true,
            button: "Add test",
          },
          also: [],
          decided_by: null,
          marks: [],
          source_tags: [],
          runs: [],
          counts: [],
          outcome: null,
          pending: 0,
          link: {
            page: "checks",
            item: null,
          },
          apart: false,
        },
        {
          id: "verify-1",
          at: "2026-11-26T04:21:50.812Z",
          area: {
            key: "observe",
            label: "Observatory and Verify",
          },
          kind: {
            key: "runs",
            label: "Runs and results",
          },
          icon: "flask",
          lead: "Verify:",
          rest: [
            {
              t: "text",
              v: " the 3 claims of your file, checked against what was found.",
            },
          ],
          who: {
            name: "You",
            source: "default",
            source_label: "No name was typed in Settings, so it reads “You”",
            demo: false,
            recorded: true,
            button: "Verify claims",
          },
          also: [],
          decided_by: "decided by fixed rules",
          marks: [],
          source_tags: [
            {
              key: "live",
              label: "Observed live",
              meaning:
                "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
              note: null,
            },
            {
              key: "lab",
              label: "Proven in the lab",
              meaning: "Run on a copy on this computer, never on your live system.",
              note: null,
            },
          ],
          runs: [
            {
              run_id: null,
              verify_run_id: 1,
              name: "localhost:46525 accepts TLS 1.3 only",
              ran_on: "localhost:46525",
              result: {
                label: "False",
                tone: "fail",
              },
              source_tag: {
                key: "live",
                label: "Observed live",
                meaning:
                  "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
                note: "Read from localhost:46525, an address in your file that you confirmed, with handshakes only.",
              },
              link: {
                page: "inventory/verify",
                item: "claim-1",
              },
            },
            {
              run_id: null,
              verify_run_id: 1,
              name: "localhost:46525 certificate is ECDSA P-256",
              ran_on: "localhost:46525",
              result: {
                label: "True",
                tone: "pass",
              },
              source_tag: {
                key: "live",
                label: "Observed live",
                meaning:
                  "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
                note: "Read from localhost:46525, an address in your file that you confirmed, with handshakes only.",
              },
              link: {
                page: "inventory/verify",
                item: "claim-2",
              },
            },
            {
              run_id: null,
              verify_run_id: 1,
              name: "signing component is acme-sign 1.4.2 implementing ECDSA P-256",
              ran_on: "acme-sign 1.4.2",
              result: {
                label: "True",
                tone: "pass",
              },
              source_tag: {
                key: "lab",
                label: "Proven in the lab",
                meaning: "Run on a copy on this computer, never on your live system.",
                note: "Checked by running a copy of acme-sign 1.4.2 on this computer. Your live system was not touched.",
              },
              link: {
                page: "inventory/verify",
                item: "claim-3",
              },
            },
          ],
          counts: [
            {
              label: "False",
              tone: "fail",
              count: 1,
            },
            {
              label: "True",
              tone: "pass",
              count: 2,
            },
          ],
          outcome: null,
          pending: 0,
          link: {
            page: "inventory/verify",
            item: null,
          },
          apart: false,
        },
        {
          id: "action-2",
          at: "2026-11-26T04:21:50.755Z",
          area: {
            key: "observe",
            label: "Observatory and Verify",
          },
          kind: {
            key: "people",
            label: "What people did",
          },
          icon: "person",
          lead: "Confirmed “I own this system”",
          rest: [
            {
              t: "text",
              v: " for ",
            },
            {
              t: "mono",
              v: "localhost:46525",
            },
            {
              t: "text",
              v: ".",
            },
          ],
          who: {
            name: "You",
            source: "default",
            source_label: "No name was typed in Settings, so it reads “You”",
            demo: false,
            recorded: true,
            button: "I own this system or am allowed to test it",
          },
          also: [],
          decided_by: null,
          marks: [],
          source_tags: [],
          runs: [],
          counts: [],
          outcome: null,
          pending: 0,
          link: {
            page: "inventory/import",
            item: null,
          },
          apart: false,
        },
        {
          id: "start-1",
          at: "2026-11-26T04:21:50.735Z",
          area: {
            key: "assessment",
            label: "The assessment",
          },
          kind: {
            key: "people",
            label: "What people did",
          },
          icon: "grid",
          lead: "Assessment 1 started",
          rest: [
            {
              t: "text",
              v: ".",
            },
          ],
          who: {
            name: "You",
            source: "default",
            source_label: "No name was typed in Settings, so it reads “You”",
            demo: false,
            recorded: true,
            button: "Use demo file",
          },
          also: [],
          decided_by: null,
          marks: [],
          source_tags: [],
          runs: [],
          counts: [],
          outcome: null,
          pending: 0,
          link: {
            page: "overview",
            item: null,
          },
          apart: false,
        },
        {
          id: "import-1",
          at: "2026-11-26T04:21:50.723Z",
          area: {
            key: "assessment",
            label: "The assessment",
          },
          kind: {
            key: "files",
            label: "Files in and out",
          },
          icon: "file",
          lead: "Brought in",
          rest: [
            {
              t: "text",
              v: " ",
            },
            {
              t: "mono",
              v: "acme-pay-cbom.json",
            },
            {
              t: "text",
              v: ": 3 claims, 1 server and 1 program.",
            },
          ],
          who: {
            name: "You",
            source: "default",
            source_label: "No name was typed in Settings, so it reads “You”",
            demo: false,
            recorded: true,
            button: "Use demo file",
          },
          also: [],
          decided_by: null,
          marks: ["Demo data"],
          source_tags: [],
          runs: [],
          counts: [],
          outcome: null,
          pending: 0,
          link: {
            page: "inventory/import",
            item: null,
          },
          apart: false,
        },
      ],
    },
  ],
  zone: "America/New_York",
  empty_text: null,
  apart: null,
  names_note:
    "Who: the account that was logged in, where the app has one (hosted, with a GitHub login); otherwise the name typed once in Settings (Who decides), or “You”. The app does not check who is at the keyboard beyond its login. Demo reviewers are Demo data. A record made before names were kept says so, and nothing is filled in afterwards.",
  disclaimer: "Passing these tests doesn't prove a system secure. It shows these specific checks passed.",
  busy: false,
};

export const runAllEntry: TimelineEntryDetail = {
  plan_id: 1,
  is_demo: true,
  entry: {
    id: "press-6",
    at: "2026-11-26T04:21:51.032Z",
    area: {
      key: "checks",
      label: "Checks",
    },
    kind: {
      key: "runs",
      label: "Runs and results",
    },
    icon: "flask",
    lead: "Run all:",
    rest: [
      {
        t: "text",
        v: " the 7 tests in the plan.",
      },
    ],
    who: {
      name: "You",
      source: "default",
      source_label: "No name was typed in Settings, so it reads “You”",
      demo: false,
      recorded: true,
      button: "Run all",
    },
    also: [],
    decided_by: "decided by the separate reviewer",
    marks: [],
    source_tags: [
      {
        key: "live",
        label: "Observed live",
        meaning:
          "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
        note: null,
      },
      {
        key: "lab",
        label: "Proven in the lab",
        meaning: "Run on a copy on this computer, never on your live system.",
        note: null,
      },
    ],
    runs: [
      {
        run_id: 1,
        verify_run_id: null,
        name: "Old TLS versions",
        ran_on: "localhost:46525",
        result: {
          label: "Failed",
          tone: "fail",
        },
        source_tag: {
          key: "live",
          label: "Observed live",
          meaning:
            "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
          note: "Read from localhost:46525, an address in your file that you confirmed, with handshakes only.",
        },
        link: {
          page: "evidence",
          item: "test-1",
        },
      },
      {
        run_id: 2,
        verify_run_id: null,
        name: "Certificate strength",
        ran_on: "localhost:46525",
        result: {
          label: "Passed",
          tone: "pass",
        },
        source_tag: {
          key: "live",
          label: "Observed live",
          meaning:
            "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
          note: "Read from localhost:46525, an address in your file that you confirmed, with handshakes only.",
        },
        link: {
          page: "evidence",
          item: "test-2",
        },
      },
      {
        run_id: 3,
        verify_run_id: null,
        name: "Attacker tricks (our short list)",
        ran_on: "acme-sign 1.4.2",
        result: {
          label: "Failed",
          tone: "fail",
        },
        source_tag: {
          key: "lab",
          label: "Proven in the lab",
          meaning: "Run on a copy on this computer, never on your live system.",
          note: "Run on a copy of acme-sign 1.4.2 on this computer. Your live system was not touched.",
        },
        link: {
          page: "evidence",
          item: "test-4",
        },
      },
      {
        run_id: 4,
        verify_run_id: null,
        name: "Independent exam (Wycheproof)",
        ran_on: "acme-sign 1.4.2",
        result: {
          label: "Failed",
          tone: "fail",
        },
        source_tag: {
          key: "lab",
          label: "Proven in the lab",
          meaning: "Run on a copy on this computer, never on your live system.",
          note: "Run on a copy of acme-sign 1.4.2 on this computer. Your live system was not touched.",
        },
        link: {
          page: "evidence",
          item: "test-3",
        },
      },
      {
        run_id: 5,
        verify_run_id: null,
        name: "Speed and size",
        ran_on: "acme-sign 1.4.2",
        result: {
          label: "Measured",
          tone: "neutral",
        },
        source_tag: {
          key: "lab",
          label: "Proven in the lab",
          meaning: "Run on a copy on this computer, never on your live system.",
          note: "Run on a copy of acme-sign 1.4.2 on this computer. Your live system was not touched.",
        },
        link: {
          page: "evidence",
          item: "test-5",
        },
      },
      {
        run_id: 6,
        verify_run_id: null,
        name: "ML-DSA-65 comparison",
        ran_on: "acme-sign 1.4.2",
        result: {
          label: "Measured",
          tone: "neutral",
        },
        source_tag: {
          key: "lab",
          label: "Proven in the lab",
          meaning: "Run on a copy on this computer, never on your live system.",
          note: "Run on a copy of acme-sign 1.4.2 on this computer. Your live system was not touched.",
        },
        link: {
          page: "evidence",
          item: "test-7",
        },
      },
      {
        run_id: 7,
        verify_run_id: null,
        name: "Post-quantum readiness",
        ran_on: "localhost:46525",
        result: {
          label: "Not offered",
          tone: "neutral",
        },
        source_tag: {
          key: "live",
          label: "Observed live",
          meaning:
            "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
          note: "Read from localhost:46525, an address in your file that you confirmed, with handshakes only.",
        },
        link: {
          page: "evidence",
          item: "test-6",
        },
      },
    ],
    counts: [
      {
        label: "Failed",
        tone: "fail",
        count: 3,
      },
      {
        label: "Passed",
        tone: "pass",
        count: 1,
      },
      {
        label: "Measured",
        tone: "neutral",
        count: 2,
      },
      {
        label: "Not offered",
        tone: "neutral",
        count: 1,
      },
    ],
    outcome: null,
    pending: 0,
    link: {
      page: "checks",
      item: null,
    },
    apart: false,
  },
  title: "Run all",
  summary: "Run all: the 7 tests in the plan.",
  people: [
    {
      role: "Started by",
      who: {
        name: "You",
        source: "default",
        source_label: "No name was typed in Settings, so it reads “You”",
        demo: false,
        recorded: true,
        button: "Run all",
      },
      at: "2026-11-26T04:21:51.032Z",
      note: null,
    },
  ],
  names_note:
    "Who: the account that was logged in, where the app has one (hosted, with a GitHub login); otherwise the name typed once in Settings (Who decides), or “You”. The app does not check who is at the keyboard beyond its login. Demo reviewers are Demo data. A record made before names were kept says so, and nothing is filled in afterwards.",
  rested_title: "What it rested on",
  rested: [],
  after_title: "What came after",
  after: [],
  record_title: "Technical record",
  record: [
    {
      label: "Entry",
      value: "press-6",
      mono: true,
    },
    {
      label: "Run 1 fingerprint (SHA-256): Old TLS versions",
      value: "4d441c7c73f70f9994ef5a916f9130c4b89f2c2745310acf56808059070a3cce",
      mono: true,
    },
    {
      label: "Run 2 fingerprint (SHA-256): Certificate strength",
      value: "741eb505818f241f9fa077770013fe98a1ae9a3c65e2a3bc15fc9689d7a96932",
      mono: true,
    },
    {
      label: "Run 3 fingerprint (SHA-256): Attacker tricks (our short list)",
      value: "3935b5f96187bf4ec005c90e910a678060db2d4f225f349958f692bd744ff58f",
      mono: true,
    },
    {
      label: "Run 4 fingerprint (SHA-256): Independent exam (Wycheproof)",
      value: "5da9f2fd97fad01f4f45f147ebd10b863a7be3d948f1e0c967718b5ef73aca83",
      mono: true,
    },
    {
      label: "Run 5 fingerprint (SHA-256): Speed and size",
      value: "5e5cf37d35a10d75d7e21b4b3fec094aad08f6ff3754cafd9f1219550beb9614",
      mono: true,
    },
    {
      label: "Run 6 fingerprint (SHA-256): ML-DSA-65 comparison",
      value: "b5d70af4d4349bd03754c229cb25b4923bfb4e93088e08b332805ad47543a136",
      mono: true,
    },
    {
      label: "Run 7 fingerprint (SHA-256): Post-quantum readiness",
      value: "11caa88318572c78f0b64340e34180ccbd277bed2349d9e2ee9b875b415a7984",
      mono: true,
    },
  ],
  link_label: "Open in Checks",
};

export const verifyEntry: TimelineEntryDetail = {
  plan_id: 1,
  is_demo: true,
  entry: {
    id: "verify-1",
    at: "2026-11-26T04:21:50.812Z",
    area: {
      key: "observe",
      label: "Observatory and Verify",
    },
    kind: {
      key: "runs",
      label: "Runs and results",
    },
    icon: "flask",
    lead: "Verify:",
    rest: [
      {
        t: "text",
        v: " the 3 claims of your file, checked against what was found.",
      },
    ],
    who: {
      name: "You",
      source: "default",
      source_label: "No name was typed in Settings, so it reads “You”",
      demo: false,
      recorded: true,
      button: "Verify claims",
    },
    also: [],
    decided_by: "decided by fixed rules",
    marks: [],
    source_tags: [
      {
        key: "live",
        label: "Observed live",
        meaning:
          "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
        note: null,
      },
      {
        key: "lab",
        label: "Proven in the lab",
        meaning: "Run on a copy on this computer, never on your live system.",
        note: null,
      },
    ],
    runs: [
      {
        run_id: null,
        verify_run_id: 1,
        name: "localhost:46525 accepts TLS 1.3 only",
        ran_on: "localhost:46525",
        result: {
          label: "False",
          tone: "fail",
        },
        source_tag: {
          key: "live",
          label: "Observed live",
          meaning:
            "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
          note: "Read from localhost:46525, an address in your file that you confirmed, with handshakes only.",
        },
        link: {
          page: "inventory/verify",
          item: "claim-1",
        },
      },
      {
        run_id: null,
        verify_run_id: 1,
        name: "localhost:46525 certificate is ECDSA P-256",
        ran_on: "localhost:46525",
        result: {
          label: "True",
          tone: "pass",
        },
        source_tag: {
          key: "live",
          label: "Observed live",
          meaning:
            "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
          note: "Read from localhost:46525, an address in your file that you confirmed, with handshakes only.",
        },
        link: {
          page: "inventory/verify",
          item: "claim-2",
        },
      },
      {
        run_id: null,
        verify_run_id: 1,
        name: "signing component is acme-sign 1.4.2 implementing ECDSA P-256",
        ran_on: "acme-sign 1.4.2",
        result: {
          label: "True",
          tone: "pass",
        },
        source_tag: {
          key: "lab",
          label: "Proven in the lab",
          meaning: "Run on a copy on this computer, never on your live system.",
          note: "Checked by running a copy of acme-sign 1.4.2 on this computer. Your live system was not touched.",
        },
        link: {
          page: "inventory/verify",
          item: "claim-3",
        },
      },
    ],
    counts: [
      {
        label: "False",
        tone: "fail",
        count: 1,
      },
      {
        label: "True",
        tone: "pass",
        count: 2,
      },
    ],
    outcome: null,
    pending: 0,
    link: {
      page: "inventory/verify",
      item: null,
    },
    apart: false,
  },
  title: "Verify",
  summary: "Verify: the 3 claims of your file, checked against what was found.",
  people: [
    {
      role: "Started by",
      who: {
        name: "You",
        source: "default",
        source_label: "No name was typed in Settings, so it reads “You”",
        demo: false,
        recorded: true,
        button: "Verify claims",
      },
      at: "2026-11-26T04:21:50.812Z",
      note: null,
    },
  ],
  names_note:
    "Who: the account that was logged in, where the app has one (hosted, with a GitHub login); otherwise the name typed once in Settings (Who decides), or “You”. The app does not check who is at the keyboard beyond its login. Demo reviewers are Demo data. A record made before names were kept says so, and nothing is filled in afterwards.",
  rested_title: "What it rested on",
  rested: [],
  after_title: "What came after",
  after: [],
  record_title: "Technical record",
  record: [
    {
      label: "Entry",
      value: "verify-1",
      mono: true,
    },
    {
      label: "Verify run 1: localhost:46525 accepts TLS 1.3 only",
      value: "False",
      mono: false,
    },
    {
      label: "Verify run 1: localhost:46525 certificate is ECDSA P-256",
      value: "True",
      mono: false,
    },
    {
      label: "Verify run 1: signing component is acme-sign 1.4.2 implementing ECDSA P-256",
      value: "True",
      mono: false,
    },
  ],
  link_label: "Open in Observatory and Verify",
};

export const decisionsView: DecisionsView = {
  plan_id: 1,
  is_demo: true,
  title: "Approvals and decisions",
  subline:
    "Every decision a person made in this assessment, with who and when. No person approves a result: the separate reviewer decides each one by fixed rules, and Results shows them.",
  cards: [
    {
      key: "decisions",
      title: "Decisions",
      value: "1",
      small: "by people, in this assessment",
    },
    {
      key: "approvals",
      title: "Approvals",
      value: "0",
      small: "of a pull request or a change",
    },
    {
      key: "otto",
      title: "Otto's proposals decided",
      value: "0",
      small: "none decided yet",
    },
    {
      key: "signoff",
      title: "Sign-off",
      value: "Not yet",
      small: "Close assessment records who and when",
    },
  ],
  names_note:
    "Who: the account that was logged in, where the app has one (hosted, with a GitHub login); otherwise the name typed once in Settings (Who decides), or “You”. The app does not check who is at the keyboard beyond its login. Demo reviewers are Demo data. A record made before names were kept says so, and nothing is filled in afterwards.",
  results_note:
    "Results are not in this list: no person decides one. Each result is the separate reviewer's (for a claim on Verify, fixed rules), and Results shows them.",
  chosen: {
    area: "all",
  },
  areas: [
    {
      key: "all",
      label: "All",
      count: 1,
    },
    {
      key: "observe",
      label: "Observatory and Verify",
      count: 1,
    },
    {
      key: "advisories",
      label: "Advisories",
      count: 0,
    },
    {
      key: "checks",
      label: "Checks",
      count: 0,
    },
    {
      key: "fixes",
      label: "Fixes",
      count: 0,
    },
    {
      key: "migration",
      label: "Migration plan",
      count: 0,
    },
    {
      key: "dependencies",
      label: "Dependencies",
      count: 0,
    },
    {
      key: "watch",
      label: "Change watch",
      count: 0,
    },
    {
      key: "assessment",
      label: "The assessment",
      count: 0,
    },
  ],
  total: 1,
  days: [
    {
      date: "2026-11-25",
      count: 1,
      rows: [
        {
          id: "action-2",
          at: "2026-11-26T04:21:50.755Z",
          decision: {
            key: "confirmed",
            label: "Confirmed “I own this system”",
          },
          on: "“I own this system” for localhost:46525",
          marks: [],
          who: {
            name: "You",
            source: "default",
            source_label: "No name was typed in Settings, so it reads “You”",
            demo: false,
            recorded: true,
            button: "I own this system or am allowed to test it",
          },
          pressed_by: null,
          area: {
            key: "observe",
            label: "Observatory and Verify",
          },
          link: {
            page: "inventory/import",
            item: null,
          },
        },
      ],
    },
  ],
  zone: "America/New_York",
  empty_text: null,
  disclaimer: "Passing these tests doesn't prove a system secure. It shows these specific checks passed.",
};

export const evidenceFilesView: EvidenceFilesView = {
  plan_id: 1,
  is_demo: true,
  title: "Evidence files",
  subline:
    "Every download of the signed evidence file, with its time, its fingerprint and who downloaded it. The JSON file is the record; the report is a readable copy and is not signed.",
  files: [],
  empty_text: "The evidence file has not been downloaded yet.",
  download: {
    can_start: true,
    blocked_reason: null,
  },
  check: {
    title: "How to check a file",
    text: "The verify command reads the JSON file as data and checks that nothing in it was changed after it was signed, and that it was signed with this app's own key. Exit code 0 only if both hold; 2 means the file is consistent but the signer could not be confirmed, which is not a pass.",
    command: "cd backend && .venv/bin/python -m evidence verify <the downloaded .json file>",
    report_note: "The report is a readable copy of the same file. It is not signed.",
  },
  holds: {
    title: "What the file holds",
    items: [
      "The imported claims and every Verify run.",
      "Every check of every kind with every run of it: the locked test, the run record, its fingerprint and the reviewer's review.",
      "Every fix: the change, each proof, the pull request, the approvals and the merge.",
      "The migration plan, every change to a system (each try, approval, Apply and Roll back) and the dependency list.",
      "Otto's part, where the assessment has one: the test packs, the ledger and every decision on a proposal.",
      "Change watch, kept apart: each developer's change and every watch run.",
      "Who did what: each recorded press with who, when, which button and the runs and records it started.",
      "The organization, project and assessment it belongs to, and the sign-off once it is closed.",
    ],
  },
  names_note:
    "Who: the account that was logged in, where the app has one (hosted, with a GitHub login); otherwise the name typed once in Settings (Who decides), or “You”. The app does not check who is at the keyboard beyond its login. Demo reviewers are Demo data. A record made before names were kept says so, and nothing is filled in afterwards.",
};

export const evidenceFilesWithOne: EvidenceFilesView = {
  plan_id: 1,
  is_demo: true,
  title: "Evidence files",
  subline:
    "Every download of the signed evidence file, with its time, its fingerprint and who downloaded it. The JSON file is the record; the report is a readable copy and is not signed.",
  files: [
    {
      id: 1,
      at: "2026-11-26T04:30:00.000Z",
      fingerprint: "5e1c7a09b3d24f6688a1c0e9d7b25f31c4a6e80b92d3f7514ac6e0b8d19f2c73",
      fingerprint_label: "Fingerprint (SHA-256)",
      who: {
        name: "You",
        source: "default",
        source_label: "No name was typed in Settings, so it reads “You”",
        demo: false,
        recorded: true,
        button: "Download evidence",
      },
      json: {
        url: "/api/evidence/1.json",
        filename: "evidence-1.json",
      },
      html: {
        url: "/api/evidence/1.html",
        filename: "evidence-1.html",
      },
    },
  ],
  empty_text: null,
  download: {
    can_start: true,
    blocked_reason: null,
  },
  check: {
    title: "How to check a file",
    text: "The verify command reads the JSON file as data and checks that nothing in it was changed after it was signed, and that it was signed with this app's own key. Exit code 0 only if both hold; 2 means the file is consistent but the signer could not be confirmed, which is not a pass.",
    command: "cd backend && .venv/bin/python -m evidence verify <the downloaded .json file>",
    report_note: "The report is a readable copy of the same file. It is not signed.",
  },
  holds: {
    title: "What the file holds",
    items: [
      "The imported claims and every Verify run.",
      "Every check of every kind with every run of it: the locked test, the run record, its fingerprint and the reviewer's review.",
      "Every fix: the change, each proof, the pull request, the approvals and the merge.",
      "The migration plan, every change to a system (each try, approval, Apply and Roll back) and the dependency list.",
      "Otto's part, where the assessment has one: the test packs, the ledger and every decision on a proposal.",
      "Change watch, kept apart: each developer's change and every watch run.",
      "Who did what: each recorded press with who, when, which button and the runs and records it started.",
      "The organization, project and assessment it belongs to, and the sign-off once it is closed.",
    ],
  },
  names_note:
    "Who: the account that was logged in, where the app has one (hosted, with a GitHub login); otherwise the name typed once in Settings (Who decides), or “You”. The app does not check who is at the keyboard beyond its login. Demo reviewers are Demo data. A record made before names were kept says so, and nothing is filled in afterwards.",
};

export const testHistory: HistoryView = {
  plan_id: 1,
  is_demo: true,
  key: "test:1",
  title: "History of this check",
  decides:
    "Who decides a result: the separate reviewer, by fixed rules, on every run. No person approves a result. What people did about it is in this history too.",
  lines: [
    {
      id: "run-8",
      at: "2026-11-26T04:22:15.185Z",
      icon: "live",
      title: "Retest on localhost:46525",
      result: {
        name: null,
        label: "Failed",
        tone: "fail",
      },
      results: [],
      who: {
        name: "You",
        source: "default",
        source_label: "No name was typed in Settings, so it reads “You”",
        demo: false,
        recorded: true,
        button: "Retest new version",
      },
      said: "started by You, with Retest new version",
      decided_by: "decided by the separate reviewer",
      note: null,
      fingerprint: "640f600ee88b133777ffec11e554cb4bcf7e84dd3f1509f8a4d30b442e2b9983",
      source_tag: {
        key: "live",
        label: "Observed live",
        meaning:
          "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
        note: "Read from localhost:46525, an address in your file that you confirmed, with handshakes only.",
      },
      marks: [],
      link: {
        page: "evidence",
        item: "retest-1-on-1",
      },
    },
    {
      id: "run-1",
      at: "2026-11-26T04:21:51.153Z",
      icon: "live",
      title: "First run on localhost:46525",
      result: {
        name: null,
        label: "Failed",
        tone: "fail",
      },
      results: [],
      who: {
        name: "You",
        source: "default",
        source_label: "No name was typed in Settings, so it reads “You”",
        demo: false,
        recorded: true,
        button: "Run all",
      },
      said: "started by You, with Run all",
      decided_by: "decided by the separate reviewer",
      note: null,
      fingerprint: "4d441c7c73f70f9994ef5a916f9130c4b89f2c2745310acf56808059070a3cce",
      source_tag: {
        key: "live",
        label: "Observed live",
        meaning:
          "Read from a system at an address in your file that you confirmed, with handshakes only. The app only observes it.",
        note: "Read from localhost:46525, an address in your file that you confirmed, with handshakes only.",
      },
      marks: [],
      link: {
        page: "evidence",
        item: "test-1",
      },
    },
    {
      id: "locked-1",
      at: "2026-11-26T04:21:50.774Z",
      icon: "clock",
      title: "Test details locked",
      result: null,
      results: [],
      who: null,
      said: null,
      decided_by: null,
      note: "before its first run on this computer · a locked test is shared by every assessment that runs it · they can't change after this · fingerprint 5b1399feaae4",
      fingerprint: null,
      source_tag: null,
      marks: [],
      link: null,
    },
  ],
  notes: [],
  empty_text: null,
  names_note:
    "Who: the account that was logged in, where the app has one (hosted, with a GitHub login); otherwise the name typed once in Settings (Who decides), or “You”. The app does not check who is at the keyboard beyond its login. Demo reviewers are Demo data. A record made before names were kept says so, and nothing is filled in afterwards.",
  timeline: {
    area: "checks",
  },
};
