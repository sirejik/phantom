using Phantom.Mapping;

namespace Phantom.UI
{
    public static class StartupWizardModel
    {
        public static string Instruction(PhantomState state,string detail="")
        {
            switch(state)
            {
                case PhantomState.Disconnected:return "Запустите симулятор на компьютере и проверьте адрес и порт UDP 31337.";
                case PhantomState.Initializing:return "Инициализация приложения и датчиков.";
                case PhantomState.RoomRequired:return "Выполните настройку пространства Meta и разрешите приложению доступ к пространственным данным.";
                case PhantomState.RobotCalibration:return "Покажите неподвижно метки основания, плеч, локтей и рабочего инструмента не менее одной секунды.";
                case PhantomState.UserCalibration:return "Встаньте в рабочей зоне. Y — начать; сделайте три большие дуги прямой рукой; Y — завершить.";
                case PhantomState.Ready:case PhantomState.ArmedHold:return "Проверьте виртуальную цель, затем удерживайте левую кнопку захвата для управления.";
                case PhantomState.Tracking:return "Управление включено. Отпустите левую кнопку захвата для немедленной остановки.";
                case PhantomState.SafeHold:return "Отпустите левую кнопку захвата, устраните причину остановки и только затем нажмите её снова.";
                case PhantomState.Fault:return "ОШИБКА: отпустите левую кнопку захвата и устраните ошибку симулятора или EV3.";
                default:return "";
            }
        }
    }
}
