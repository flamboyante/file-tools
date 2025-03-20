
class PowerControl:

    power_status_dict = \
        {
            'BS0': False,
            'BS1': False,
            'BS2': False,
            'BS3': False,
            'COD0': False,
            'COD1': False,
            'SW0': False,
            'SW1': False,
            'SC BS4': False,
            'SC BS5': False,
            'SC COD0': False,
            '5396': False
        }

    power_off_dict = \
        {
            'BS0': '10',
            'BS1': '20',
            'BS2': '30',
            'BS3': '40',
            'COD0': '50',
            'COD1': '60',
            'SW0': '70',
            'SW1': '00',
            'SC BS4': '80',
            'SC BS5': '90',
            'SC COD0': 'a0',
            '5396': '5396'
        }

    power_on_dict = \
        {
            'BS0': '11',
            'BS1': '21',
            'BS2': '31',
            'BS3': '41',
            'COD0': '51',
            'COD1': '61',
            'SW0': '71',
            'SW1': '01',
            'SC BS4': '81',
            'SC BS5': '91',
            'SC COD0': 'a1',
            '5396': '5396'
        }

    @classmethod
    def set_power_status(cls, component: str, status: bool) -> bool:
        ret = False
        try:
            cls.power_status_dict[component] = status
            ret = True
        except Exception as e:
            print(str(e))
            raise
        finally:
            return ret

    @classmethod
    def get_power_status(cls, component: str) -> bool:
        status = bool(None)
        try:
            status = cls.power_status_dict.get(component)
        except Exception as e:
            print(str(e))
            raise
        finally:
            return status

    @classmethod
    def get_power_on_cmd(cls, component: str) -> str:
        cmd = str(None)
        try:
            cmd = cls.power_on_dict.get(component)
        except Exception as e:
            print(str(e))
            raise
        finally:
            return cmd

    @classmethod
    def get_power_off_cmd(cls, component: str) -> str:
        cmd = str(None)
        try:
            cmd = cls.power_off_dict.get(component)
        except Exception as e:
            print(str(e))
            raise
        finally:
            return cmd
