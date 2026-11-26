import { NavLink } from "react-router-dom";
import { useApp } from "../../context/AppContext";
import { Avatar, AvatarFallback, AvatarImage } from "../ui/avatar";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../ui/tooltip";
import { StoreHealthStrip } from "./StoreHealthStrip";
import {
  LayoutDashboard,
  MessageSquareQuote,
  FileText,
  Network,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";

export function Sidebar() {
  const { sidebarCollapsed, setSidebarCollapsed } = useApp();

  const navGroups = [
    {
      group: "Workspace",
      items: [
        { label: "Overview", to: "/overview", icon: LayoutDashboard },
        { label: "Ask", to: "/", icon: MessageSquareQuote, badge: "Glass-Box" },
        { label: "Documents", to: "/documents", icon: FileText },
        { label: "Graph", to: "/graph", icon: Network },
      ],
    },
  ];

  return (
    <TooltipProvider delayDuration={100}>
      <aside
        className={`border-r border-zinc-800/80 bg-zinc-950 flex flex-col justify-between shrink-0 transition-all duration-300 z-30 select-none ${
          sidebarCollapsed ? "w-16" : "w-60"
        }`}
      >
        {/* Workspace Brand Header */}
        <div>
          <div className="h-14 px-3.5 border-b border-zinc-800/80 flex items-center justify-between">
            {!sidebarCollapsed ? (
              <div className="flex items-center gap-2.5">
                <div className="h-7 w-7 rounded-lg bg-zinc-100 text-zinc-950 flex items-center justify-center font-black text-xs tracking-tighter shadow-sm">
                  G
                </div>
                <div>
                  <div className="font-semibold text-xs text-zinc-100 tracking-tight leading-none">
                    Grant Lab
                  </div>
                  <div className="text-[10px] text-zinc-500 font-mono mt-0.5">GraphRAG Glass-Box</div>
                </div>
              </div>
            ) : (
              <div className="h-7 w-7 mx-auto rounded-lg bg-zinc-100 text-zinc-950 flex items-center justify-center font-black text-xs">
                G
              </div>
            )}
            <button
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              className="p-1 rounded-md text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900 transition-colors cursor-pointer"
              title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {sidebarCollapsed ? <PanelLeftOpen className="h-3.5 w-3.5" /> : <PanelLeftClose className="h-3.5 w-3.5" />}
            </button>
          </div>

          {/* Navigation Groups */}
          <div className="p-2 space-y-4">
            {navGroups.map((grp) => (
              <div key={grp.group} className="space-y-1">
                {!sidebarCollapsed && (
                  <div className="px-2.5 text-[10px] font-mono uppercase tracking-wider text-zinc-500 font-semibold mb-1">
                    {grp.group}
                  </div>
                )}
                {grp.items.map((item) => {
                  const Icon = item.icon;
                  const linkElement = (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === "/"}
                      className={({ isActive }) =>
                        `flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
                          isActive
                            ? "bg-zinc-800 text-zinc-100 shadow-xs font-semibold"
                            : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
                        } ${sidebarCollapsed ? "justify-center px-0" : ""}`
                      }
                    >
                      <Icon className="h-4 w-4 shrink-0" />
                      {!sidebarCollapsed && (
                        <div className="flex-1 flex items-center justify-between">
                          <span>{item.label}</span>
                          {item.badge && (
                            <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-purple-950 text-purple-300 border border-purple-800/60">
                              {item.badge}
                            </span>
                          )}
                        </div>
                      )}
                    </NavLink>
                  );

                  if (sidebarCollapsed) {
                    return (
                      <Tooltip key={item.to}>
                        <TooltipTrigger asChild>{linkElement}</TooltipTrigger>
                        <TooltipContent side="right">
                          <span>{item.label}</span>
                        </TooltipContent>
                      </Tooltip>
                    );
                  }

                  return linkElement;
                })}
              </div>
            ))}
          </div>
        </div>

        {/* Sidebar Footer */}
        <div className="p-3 border-t border-zinc-800/80 space-y-3">
          {/* Store Health Strip */}
          <StoreHealthStrip compact={sidebarCollapsed} />

          {/* Settings Nav */}
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
                isActive
                  ? "bg-zinc-800 text-zinc-100 font-semibold"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
              } ${sidebarCollapsed ? "justify-center px-0" : ""}`
            }
          >
            <Settings className="h-4 w-4 shrink-0" />
            {!sidebarCollapsed && <span>Settings</span>}
          </NavLink>

          {/* User Profile */}
          <div className={`flex items-center gap-2.5 p-1 rounded-lg hover:bg-zinc-900 transition-colors cursor-pointer ${sidebarCollapsed ? "justify-center" : ""}`}>
            <Avatar className="h-7 w-7">
              <AvatarImage src="https://avatar.vercel.sh/grant" />
              <AvatarFallback className="text-[10px]">MA</AvatarFallback>
            </Avatar>
            {!sidebarCollapsed && (
              <div className="truncate text-left leading-tight">
                <div className="text-xs font-medium text-zinc-200">Mahil Arasan</div>
                <div className="text-[10px] text-zinc-500 font-mono truncate">mahil@grant.lab</div>
              </div>
            )}
          </div>
        </div>
      </aside>
    </TooltipProvider>
  );
}
