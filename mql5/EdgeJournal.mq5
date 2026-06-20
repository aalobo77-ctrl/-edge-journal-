//+------------------------------------------------------------------+
//| EdgeJournal.mq5 - MT5 Trade Sync EA                              |
//| Sends closed trades to the Edge Journal API                      |
//+------------------------------------------------------------------+
#property copyright "Edge Journal"
#property version "1.00"
#property description "Syncs trades to Edge Journal automatically"
#property script_show_inputs

input string API_URL = "https://aal77.pythonanywhere.com";
input int    API_USER_ID = 1;
input int    SyncInterval = 300;
input bool   SyncOnStartup = true;

string lastSyncFile = "EdgeJournal_last_sync.txt";
string lastSyncTime;

int OnInit() {
   lastSyncTime = GetLastSyncTime();
   if (SyncOnStartup) SyncHistory();
   EventSetTimer(SyncInterval);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason) { EventKillTimer(); }
void OnTimer() { SyncHistory(); }
void OnTrade() { SyncHistory(); }

void SyncHistory() {
   datetime from = StringToTime(lastSyncTime);
   HistorySelect(from, TimeCurrent());
   for (int i = HistoryDealsTotal() - 1; i >= 0; i--) {
      ulong ticket = HistoryDealGetTicket(i);
      if (ticket <= 0) continue;
      ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket, DEAL_ENTRY);
      if (entry != DEAL_ENTRY_OUT) continue;
      string symbol = HistoryDealGetString(ticket, DEAL_SYMBOL);
      double profit = HistoryDealGetDouble(ticket, DEAL_PROFIT);
      double volume = HistoryDealGetDouble(ticket, DEAL_VOLUME);
      double price = HistoryDealGetDouble(ticket, DEAL_PRICE);
      double commission = HistoryDealGetDouble(ticket, DEAL_COMMISSION);
      datetime time = (datetime)HistoryDealGetInteger(ticket, DEAL_TIME);
      ENUM_DEAL_TYPE type = (ENUM_DEAL_TYPE)HistoryDealGetInteger(ticket, DEAL_TYPE);
      string direction = (type == DEAL_TYPE_BUY) ? "LONG" : "SHORT";
      string json = "{\"user_id\":" + IntegerToString(API_USER_ID) + ",";
      json += "\"symbol\":\"" + symbol + "\",\"direction\":\"" + direction + "\",";
      json += "\"volume\":" + DoubleToString(volume,2) + ",";
      json += "\"entry_price\":" + DoubleToString(price,2) + ",";
      json += "\"exit_price\":" + DoubleToString(price,2) + ",";
      json += "\"profit\":" + DoubleToString(profit,2) + ",";
      json += "\"commission\":" + DoubleToString(commission,2) + ",";
      json += "\"entry_time\":\"" + TimeToString(time,TIME_DATE|TIME_SECONDS) + "\",";
      json += "\"exit_time\":\"" + TimeToString(time,TIME_DATE|TIME_SECONDS) + "\"}";
      string headers = "Content-Type: application/json\r\n";
      char data[], result[];
      StringToCharArray(json, data);
      ResetLastError();
      WebRequest("POST", API_URL + "/api/sync/trade", headers, 5000, data, result, headers);
   }
   lastSyncTime = TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS);
   SaveLastSyncTime(lastSyncTime);
}

string GetLastSyncTime() {
   string data;
   int h = FileOpen(lastSyncFile, FILE_READ|FILE_TXT);
   if (h != INVALID_HANDLE) { data = FileReadString(h); FileClose(h); }
   return (data != "") ? data : "2020-01-01 00:00:00";
}

void SaveLastSyncTime(string t) {
   int h = FileOpen(lastSyncFile, FILE_WRITE|FILE_TXT);
   if (h != INVALID_HANDLE) { FileWriteString(h, t); FileClose(h); }
}
