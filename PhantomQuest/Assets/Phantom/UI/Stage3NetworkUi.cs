using Phantom.Networking;

namespace Phantom.UI
{
    public static class Stage3NetworkUi
    {
        public static string Format(NetworkSnapshot value,bool diagnostic=true)
        {
            if(value==null)return "PHANTOM\n\nОШИБКА КОНФИГУРАЦИИ";
            var headline=Headline(value);
            if(!value.SessionActive)return "PHANTOM\n\n"+headline+(value.ServiceFound?"\n\nНАЙДЕН PHANTOM "+value.RobotId:"");
            var telemetry=value.Freshness==TelemetryFreshness.Fresh?"АКТУАЛЬНА":value.Freshness==TelemetryFreshness.Stale?"УСТАРЕЛА":value.Freshness==TelemetryFreshness.Invalid?"ОШИБКА":"ОЖИДАНИЕ";
            var battery=value.BatteryMv==0?"Н/Д":(value.BatteryMv/1000.0).ToString("F2",System.Globalization.CultureInfo.InvariantCulture)+" В";
            var text="PHANTOM\n\n"+headline+"\n\nРОБОТ        СОЕДИНЁН\nСЕССИЯ       АКТИВНА\nСОСТОЯНИЕ    "+value.RemoteState+"\nОШИБКА EV3   "+value.Fault+"\nБАТАРЕЯ      "+battery+"\nТЕЛЕМЕТРИЯ   "+telemetry;
            if(diagnostic)text+="\n\nENDPOINT     "+value.Endpoint+"\nRTT          "+(value.RttMilliseconds<0?"Н/Д":value.RttMilliseconds.ToString("F0")+" мс")+"\nBUILD        "+Safe(value.BuildId)+"\nBOOT         "+Safe(value.ControllerBootId)+"\nPROTOCOL     "+Safe(value.ProtocolHash)+"\nCONFIG       "+Safe(value.BundleHash)+"\nPACKETS      "+value.AcceptedPackets+" OK / "+value.RejectedPackets+" DROP";
            return text;
        }

        static string Headline(NetworkSnapshot value)
        {
            switch(value.State)
            {
                case NetworkState.Idle:return "РОБОТ НЕ НАЙДЕН";
                case NetworkState.Discovering:return "ИЩУ РОБОТА…";
                case NetworkState.Resolving:return "НАЙДЕН PHANTOM "+value.RobotId;
                case NetworkState.Handshaking:return "ПОДКЛЮЧЕНИЕ…";
                case NetworkState.Connected:case NetworkState.TelemetryFresh:return "СОЕДИНЕНО";
                case NetworkState.TelemetryStale:return "ТЕЛЕМЕТРИЯ УСТАРЕЛА";
                case NetworkState.Reconnecting:return "ПОВТОРНОЕ ПОДКЛЮЧЕНИЕ";
                case NetworkState.ProtocolMismatch:return "НЕСОВМЕСТИМАЯ ВЕРСИЯ";
                case NetworkState.ConfigurationMismatch:return "ОШИБКА КОНФИГУРАЦИИ";
                case NetworkState.AuthenticationFailure:return "ОШИБКА АУТЕНТИФИКАЦИИ";
                default:return "ПОТЕРЯНО СОЕДИНЕНИЕ";
            }
        }
        static string Safe(string value)=>string.IsNullOrEmpty(value)?"Н/Д":value;
    }
}
