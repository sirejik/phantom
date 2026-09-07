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
            var text="PHANTOM\n\n"+headline+"\n\nРОБОТ        СОЕДИНЁН\nСЕССИЯ       АКТИВНА\nСОСТОЯНИЕ    "+RobotState(value.RemoteState)+"\nОШИБКА EV3   "+Fault(value.Fault)+"\nБАТАРЕЯ      "+battery+"\nТЕЛЕМЕТРИЯ   "+telemetry;
            if(diagnostic)text+="\n\nENDPOINT     "+value.Endpoint+"\nRTT          "+(value.RttMilliseconds<0?"Н/Д":value.RttMilliseconds.ToString("F0")+" мс")+"\nBUILD        "+Safe(value.BuildId)+"\nBOOT         "+Safe(value.ControllerBootId)+"\nPROTOCOL     "+Safe(value.ProtocolHash)+"\nCONFIG       "+Safe(value.BundleHash)+"\nПАКЕТЫ       "+value.AcceptedPackets+" принято / "+value.RejectedPackets+" отклонено";
            return text;
        }

        /// <summary>Russian robot state, never a raw C# enum name (FR-UI-01).</summary>
        public static string RobotState(RobotRuntimeState value)
        {
            switch(value)
            {
                case RobotRuntimeState.Boot:return "ЗАГРУЗКА";
                case RobotRuntimeState.UserCalibration:return "КАЛИБРОВКА ПОЛЬЗОВАТЕЛЯ";
                case RobotRuntimeState.Discovery:return "ПОИСК СЕССИИ";
                case RobotRuntimeState.ConnectedUnreferenced:return "СОЕДИНЁН, БЕЗ ПРИВЯЗКИ";
                case RobotRuntimeState.RobotCalibration:return "КАЛИБРОВКА РОБОТА";
                case RobotRuntimeState.Ready:return "ГОТОВНОСТЬ";
                case RobotRuntimeState.Hold:return "УДЕРЖАНИЕ";
                case RobotRuntimeState.Tracking:return "СЛЕЖЕНИЕ";
                case RobotRuntimeState.SafeHold:return "БЕЗОПАСНОЕ УДЕРЖАНИЕ";
                case RobotRuntimeState.Stopped:return "ОСТАНОВЛЕН";
                case RobotRuntimeState.Commissioning:return "ИНЖЕНЕРНЫЙ РЕЖИМ";
                default:return "НЕИЗВЕСТНОЕ СОСТОЯНИЕ";
            }
        }

        /// <summary>Russian fault description; the numeric code stays as provenance.</summary>
        public static string Fault(ushort code)
        {
            if(code==0)return "НЕТ";
            string text;
            switch(code)
            {
                case 100:text="ТАЙМАУТ КОМАНДЫ";break;
                case 101:text="ОШИБКА КОНФИГУРАЦИИ";break;
                case 102:text="ВЫХОД ЗА ГРАНИЦЫ";break;
                case 103:text="ЗАКЛИНИВАНИЕ СУСТАВА";break;
                case 104:text="ОШИБКА ЗАХВАТА";break;
                case 105:text="НЕТ ПРИВЯЗКИ";break;
                case 106:text="ОШИБКА ЛОКАЛИЗАЦИИ";break;
                case 107:text="ПОТЕРЯ ПРОЦЕССА БЕЗОПАСНОСТИ";break;
                case 108:text="ПРЕВЫШЕНИЕ ПЕРИОДА ЦИКЛА";break;
                case 109:text="ОШИБКА БЕЗОПАСНОСТИ";break;
                case 110:text="ПЕРЕГРУЗКА МОТОРА";break;
                case 111:text="ОШИБКА РАБОЧЕЙ ОБЛАСТИ";break;
                case 112:text="ОШИБКА GRIPPER_HOME";break;
                case 113:text="ОШИБКА МОДЕЛИ КОЛЛИЗИЙ";break;
                case 114:text="ОШИБКА PAYLOAD PROFILE";break;
                case 115:text="ПЕРЕГРУЗКА ПРИ УДЕРЖАНИИ";break;
                case 116:text="НИЗКИЙ ЗАРЯД БАТАРЕИ";break;
                default:text="НЕИЗВЕСТНАЯ ОШИБКА";break;
            }
            return text+" ("+code+")";
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
