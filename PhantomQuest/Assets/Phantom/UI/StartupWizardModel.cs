using Phantom.Mapping;

namespace Phantom.UI
{
    public static class StartupWizardModel
    {
        public static string Instruction(PhantomState state,string detail="")
        {
            switch(state)
            {
                case PhantomState.Boot:return "Проверьте OpenXR, LOCAL_FLOOR, Spatial Data и QR Trackables.";
                case PhantomState.Discovery:return "Идёт поиск PHANTOM EV3 по имени робота в локальной сети.";
                case PhantomState.ConnectedUnreferenced:return "Покажите все QR-маркеры для привязки энкодеров.";
                case PhantomState.RobotCalibration:return "Покажите неподвижно метки основания, плеч, локтей и рабочего инструмента не менее одной секунды.";
                case PhantomState.UserCalibration:return "Встаньте в рабочей зоне. Y — начать; сделайте три большие дуги прямой рукой; Y — завершить.";
                case PhantomState.Ready:case PhantomState.Hold:return "Проверьте виртуальную цель, отпустите и затем заново нажмите левую кнопку захвата.";
                case PhantomState.Tracking:return "Управление включено. Отпустите левую кнопку захвата для немедленной остановки.";
                case PhantomState.SafeHold:return "Отпустите левую кнопку захвата, устраните причину остановки и только затем нажмите её снова.";
                case PhantomState.Fault:return "ОШИБКА: отпустите левую кнопку захвата и устраните ошибку симулятора или EV3.";
                default:return "";
            }
        }
    }
}
