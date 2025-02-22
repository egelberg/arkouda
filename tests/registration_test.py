import json

import pytest
from base_test import ArkoudaTest
from context import arkouda as ak

from arkouda import Series
from arkouda.pdarrayclass import RegistrationError, unregister_pdarray_by_name

N = 100
UNIQUE = N // 4


class RegistrationTest(ArkoudaTest):
    def setUp(self):
        ArkoudaTest.setUp(self)
        self.a_array = ak.ones(10, dtype=ak.int64)
        self.b_array = ak.ones(10, dtype=ak.int64)

    def test_register(self):
        """
        Tests the following:

        1. register invocation
        2. pdarray.name matches register name
        3. original and registered pdarray are equal
        4. method invocation on a cleared, registered array succeeds
        """
        ar_array = self.a_array.register("test_int64_a")

        self.assertEqual("test_int64_a", self.a_array.name, "Expect name to change inplace")
        self.assertTrue(self.a_array is ar_array, "These should be the same object")
        self.assertListEqual(self.a_array.to_list(), ar_array.to_list())
        ak.clear()
        # Both ar_array and self.a_array point to the same object, so both should still be usable.
        str(ar_array)
        str(self.a_array)

        try:
            self.a_array.unregister()
        except (RuntimeError, RegistrationError):
            pass  # Will be tested in `test_unregister`

    def test_double_register(self):
        """
        Tests the case when two objects get registered using the same user_defined_name
        """
        a = ak.ones(3, dtype=ak.int64)
        b = ak.ones(3, dtype=ak.int64)
        b.fill(2)
        a.register("foo")

        with self.assertRaises(RegistrationError, msg="Should raise an Error"):
            b.register("foo")

        # Clean up the registry
        a.unregister()

    def test_registration_type_check(self):
        """
        Tests type checking of user_defined_name for register and attach
        """

        a = ak.ones(3, dtype=ak.int64)

        with self.assertRaises(
            TypeError, msg="register() should raise TypeError when user_defined_name is not a str"
        ):
            a.register(7)
        with self.assertRaises(
            TypeError, msg="attach() should raise TypeError when user_defined_name is not a str"
        ):
            a.attach(7)

        ak.clear()

    def test_unregister(self):
        """
        Tests the following:

        1. unregister invocation
        2. method invocation on a cleared, unregistered array raises RuntimeError
        """
        ar_array = self.a_array.register("test_int64_a")

        self.assertEqual("[1 1 1 1 1 1 1 1 1 1]", str(ar_array))
        ar_array.unregister()
        self.assertEqual("[1 1 1 1 1 1 1 1 1 1]", str(ar_array))

        ak.clear()

        with self.assertRaises(RuntimeError):
            str(ar_array)

        with self.assertRaises(RuntimeError):
            repr(ar_array)

    def test_attach(self):
        """
        Tests the following:

        1. Attaching to a registered pdarray
        2. The registered and attached pdarrays are equal
        3. The attached pdarray is deleted server-side following
           unregister of registered pdarray and invocation of
           ak.clear()
        4. method invocation on cleared attached array raises RuntimeError
        """
        ar_array = self.a_array.register("test_int64_a")
        aar_array = ak.attach_pdarray("test_int64_a")

        self.assertEqual(ar_array.name, aar_array.name)
        self.assertListEqual(ar_array.to_list(), aar_array.to_list())

        ak.disconnect()
        ak.connect(server=ArkoudaTest.server, port=ArkoudaTest.port)
        aar_array = ak.attach_pdarray("test_int64_a")

        self.assertEqual(ar_array.name, aar_array.name)
        self.assertListEqual(ar_array.to_list(), aar_array.to_list())

        ar_array.unregister()
        ak.clear()

        with self.assertRaises(RuntimeError):
            str(aar_array)

        with self.assertRaises(RuntimeError):
            repr(aar_array)

    def test_clear(self):
        """
        Tests the following:

        1. clear() removes server-side pdarrays that are unregistered
        2. Registered pdarrays remain after ak.clear()
        3. All cleared pdarrays throw RuntimeError upon method invocation
        4. Method invocation on registered arrays succeeds after ak.clear()
        """
        ar_array = self.a_array.register("test_int64_a")
        aar_array = self.a_array.register("test_int64_aa")

        self.assertTrue(ar_array is aar_array, msg="With inplace modification, these should be the same")
        self.assertEqual(
            ar_array.name,
            "test_int64_aa",
            msg="ar_array.name should be updated with inplace modification",
        )

        twos_array = ak.ones(10, dtype=ak.int64).register("twos_array")
        twos_array.fill(2)

        g_twos_array = self.a_array + self.b_array
        self.assertListEqual(twos_array.to_list(), g_twos_array.to_list())

        ak.clear()  # This should remove self.b_array and g_twos_array

        with self.assertRaises(
            RuntimeError, msg="g_twos_array should have been cleared because it wasn't registered"
        ):
            str(g_twos_array)

        with self.assertRaises(
            RuntimeError, msg="self.b_array should have been cleared because it wasn't registered"
        ):
            str(self.b_array)

        # Assert these exist by invoking them and not receiving an exception
        str(self.a_array)
        str(ar_array)

        with self.assertRaises(RuntimeError, msg="Should raise error because self.b_array was cleared"):
            self.a_array + self.b_array

        g_twos_array = ar_array + aar_array
        self.assertListEqual(twos_array.to_list(), g_twos_array.to_list())

    def test_register_info(self):
        """
        Tests the following:

        1. json.loads(info(AllSymbols)) is an empty list when the symbol table is empty
        2. json.loads(info(RegisteredSymbols)) is an empty list when the registry is empty
        3. The registered field is set to false for objects that have not been registered
        4. The registered field is set to true for objects that have been registered
        5. info(ak.AllSymbols) contains both registered and non-registered objects
        6. info(ak.RegisteredSymbols) only contains registered objects
        7. info raises RunTimeError when called on objects not found in symbol table
        """
        # Cleanup symbol table from previous tests
        cleanup()

        self.assertFalse(
            json.loads(ak.information(ak.AllSymbols)), msg="info(AllSymbols) should be empty list"
        )
        self.assertFalse(
            json.loads(ak.information(ak.RegisteredSymbols)),
            msg="info(RegisteredSymbols) should be empty list",
        )

        my_pdarray = ak.ones(10, dtype=ak.int64)
        self.assertFalse(
            json.loads(my_pdarray.info())[0]["registered"],
            msg="my_array should be in all symbols but not be registered",
        )

        # After register(), the registered field should be set to true for all info calls
        my_pdarray.register("keep_me")
        self.assertTrue(
            json.loads(ak.information("keep_me"))[0]["registered"],
            msg="keep_me array not found or not registered",
        )
        self.assertTrue(
            any([sym["registered"] for sym in json.loads(ak.information(ak.AllSymbols))]),
            msg="No registered objects were found in symbol table",
        )
        self.assertTrue(
            any([sym["registered"] for sym in json.loads(ak.information(ak.RegisteredSymbols))]),
            msg="No registered objects were found in registry",
        )

        not_registered_array = ak.ones(10, dtype=ak.int64)
        self.assertTrue(
            len(json.loads(ak.information(ak.AllSymbols)))
            > len(json.loads(ak.information(ak.RegisteredSymbols))),
            msg="info(AllSymbols) should have more objects than info(RegisteredSymbols) before clear()",
        )
        ak.clear()
        self.assertEqual(
            len(json.loads(ak.information(ak.AllSymbols))),
            len(json.loads(ak.information(ak.RegisteredSymbols))),
            msg="info(AllSymbols) and info(RegisteredSymbols) should have same num of objects "
            "after clear()",
        )

        # After unregister(), the registered field should be set to false for AllSymbol and
        # object name info calls
        # RegisteredSymbols info calls should return ak.EmptyRegistry
        my_pdarray.unregister()
        self.assertFalse(
            any([obj["registered"] for obj in json.loads(my_pdarray.info())]),
            msg="info(my_array) registered field should be false after unregister()",
        )
        self.assertFalse(
            all([obj["registered"] for obj in json.loads(ak.information(ak.AllSymbols))]),
            msg="info(AllSymbols) should contain unregistered objects",
        )
        self.assertFalse(
            json.loads(ak.information(ak.RegisteredSymbols)),
            msg="info(RegisteredSymbols) empty list failed after unregister()",
        )

        ak.clear()
        # RuntimeError when calling info on an object not in the symbol table
        with self.assertRaises(RuntimeError, msg="RuntimeError for info on object not in symbol table"):
            ak.information("keep_me")
        self.assertFalse(
            json.loads(ak.information(ak.AllSymbols)), msg="info(AllSymbols) should be empty list"
        )
        self.assertFalse(
            json.loads(ak.information(ak.RegisteredSymbols)),
            msg="info(RegisteredSymbols) should be empty list",
        )
        cleanup()

    def test_in_place_info(self):
        """
        Tests the class level info method for pdarray, String, and Categorical
        """
        cleanup()
        my_pda = ak.ones(10, ak.int64)
        self.assertFalse(
            any([sym["registered"] for sym in json.loads(my_pda.info())]),
            msg="no components of my_pda should be registered before register call",
        )
        my_pda.register("my_pda")
        self.assertTrue(
            all([sym["registered"] for sym in json.loads(my_pda.info())]),
            msg="all components of my_pda should be registered after register call",
        )

        my_str = ak.random_strings_uniform(1, 10, UNIQUE, characters="printable")
        self.assertFalse(
            any([sym["registered"] for sym in json.loads(my_str.info())]),
            msg="no components of my_str should be registered before register call",
        )
        my_str.register("my_str")
        self.assertTrue(
            all([sym["registered"] for sym in json.loads(my_str.info())]),
            msg="all components of my_str should be registered after register call",
        )

        my_cat = ak.Categorical(ak.array([f"my_cat {i}" for i in range(1, 11)]))
        self.assertFalse(
            any([sym["registered"] for sym in json.loads(my_cat.info())]),
            msg="no components of my_cat should be registered before register call",
        )
        my_cat.register("my_cat")
        self.assertTrue(
            all([sym["registered"] for sym in json.loads(my_cat.info())]),
            msg="all components of my_cat should be registered after register call",
        )
        cleanup()

    def test_is_registered(self):
        """
        Tests the pdarray.is_registered() function
        """
        cleanup()
        a = ak.ones(10, dtype=ak.int64)
        self.assertFalse(a.is_registered())

        a.register("keep")
        self.assertTrue(a.is_registered())

        a.unregister()
        self.assertFalse(a.is_registered())
        ak.clear()

    def test_list_registry(self):
        """
        Tests the generic ak.list_registry() function
        """
        cleanup()
        # Test list_registry when the symbol table is empty
        self.assertFalse(ak.list_registry(), "registry should be empty")

        a = ak.ones(10, dtype=ak.int64)
        # list_registry() should return an empty list which is implicitly False
        self.assertFalse(ak.list_registry())

        a.register("keep")
        self.assertTrue("keep" in ak.list_registry())
        cleanup()

    def test_string_registration_suite(self):
        cleanup()
        # Initial registration should set name
        keep = ak.random_strings_uniform(1, 10, UNIQUE, characters="printable")
        self.assertEqual(keep.register("keep_me").name, "keep_me")
        self.assertTrue(keep.is_registered(), "Expected Strings object to be registered")

        # Register a second time to confirm name change
        self.assertEqual(keep.register("kept").name, "kept")
        self.assertTrue(keep.is_registered(), "Object should be registered with updated name")

        # Add an item to discard, confirm our registered item remains and discarded item is gone
        discard = ak.random_strings_uniform(1, 10, UNIQUE, characters="printable")
        ak.clear()
        self.assertEqual(keep.name, "kept")
        with self.assertRaises(RuntimeError, msg="discard was not registered and should be discarded"):
            str(discard)

        # Unregister, should remain usable until we clear
        keep.unregister()
        str(keep)  # Should not cause error
        self.assertFalse(keep.is_registered(), "This item should no longer be registered")
        ak.clear()
        with self.assertRaises(RuntimeError, msg="keep was unregistered and should be cleared"):
            str(keep)  # should cause RuntimeError

        # Test attach functionality
        s1 = ak.random_strings_uniform(1, 10, UNIQUE, characters="printable")
        self.assertTrue(s1.register("uut").is_registered(), "uut should be registered")
        s1 = None
        self.assertTrue(s1 is None, "Reference should be cleared")
        s1 = ak.Strings.attach("uut")
        self.assertTrue(s1.is_registered(), "Should have re-attached to registered object")
        str(s1)  # This will throw an exception if the object doesn't exist server-side

        # Test the Strings unregister by name using previously registered object
        ak.Strings.unregister_strings_by_name("uut")
        self.assertFalse(s1.is_registered(), "Expected object to be unregistered")
        cleanup()

    def test_string_is_registered(self):
        """
        Tests the Strings.is_registered() function
        """
        keep = ak.random_strings_uniform(1, 10, UNIQUE, characters="printable")
        self.assertFalse(keep.is_registered())

        keep.register("keep_me")
        self.assertTrue(keep.is_registered())

        keep.unregister()
        self.assertFalse(keep.is_registered())

        ak.clear()

    def test_delete_registered(self):
        """
        Tests the following:

        1. delete cmd doesn't delete registered objects and returns appropriate message
        2. delete cmd does delete non-registered objects and returns appropriate message
        3. delete cmd raises RuntimeError for unknown symbols
        """
        cleanup()
        a = ak.ones(3, dtype=ak.int64)
        b = ak.ones(3, dtype=ak.int64)

        # registered objects are not deleted from symbol table
        a.register("keep")
        self.assertEqual(
            ak.client.generic_msg(cmd="delete", args={"name": a.name}),
            f"registered symbol, " f"{a.name}, not deleted",
        )
        self.assertTrue(a.name in ak.list_symbol_table())

        # non-registered objects are deleted from symbol table
        self.assertEqual(ak.client.generic_msg(cmd="delete", args={"name": b.name}), "deleted " + b.name)
        self.assertTrue(b.name not in ak.list_symbol_table())

        # RuntimeError when calling delete on an object not in the symbol table
        with self.assertRaises(RuntimeError):
            ak.client.generic_msg(cmd="delete", args={"name": "not_in_table"})

    def test_categorical_registration_suite(self):
        """
        Test register, is_registered, attach, unregister, unregister_categorical_by_name
        """
        cleanup()  # Make sure we start with a clean registry
        c = ak.Categorical(ak.array([f"my_cat {i}" for i in range(1, 11)]))
        self.assertFalse(c.is_registered(), "test_me should be unregistered")
        self.assertTrue(
            c.register("test_me").is_registered(), "test_me categorical should be registered"
        )
        c = None  # Should trigger destructor, but survive server deletion because it is registered
        self.assertTrue(c is None, "The reference to `c` should be None")
        c = ak.Categorical.attach("test_me")
        self.assertTrue(c.is_registered(), "test_me categorical should be registered after attach")
        c.unregister()
        self.assertFalse(c.is_registered(), "test_me should be unregistered")
        self.assertEqual(c.register("another_name").name, "another_name")
        self.assertTrue(c.is_registered())

        # Test static unregister_by_name
        ak.Categorical.unregister_categorical_by_name("another_name")
        self.assertFalse(c.is_registered(), "another_name should be unregistered")

        # now mess with the subcomponents directly to test is_registered mis-match logic
        c.register("another_name")
        unregister_pdarray_by_name("another_name.codes")
        with pytest.raises(RegistrationError):
            c.is_registered()

    def test_categorical_from_codes_registration_suite(self):
        """
        Test register, is_registered, attach, unregister, unregister_categorical_by_name
        for Categorical made using .from_codes
        """
        cleanup()  # Make sure we start with a clean registry
        categories = ak.array(["a", "b", "c"])
        codes = ak.array([0, 1, 0, 2, 1])
        cat = ak.Categorical.from_codes(codes, categories)
        self.assertFalse(cat.is_registered(), "test_me should be unregistered")
        self.assertTrue(
            cat.register("test_me").is_registered(), "test_me categorical should be registered"
        )
        cat = None  # Should trigger destructor, but survive server deletion because it is registered
        self.assertTrue(cat is None, "The reference to `c` should be None")
        cat = ak.Categorical.attach("test_me")
        self.assertTrue(cat.is_registered(), "test_me categorical should be registered after attach")
        cat.unregister()
        self.assertFalse(cat.is_registered(), "test_me should be unregistered")
        self.assertEqual(cat.register("another_name").name, "another_name")
        self.assertTrue(cat.is_registered())

        # Test static unregister_by_name
        ak.Categorical.unregister_categorical_by_name("another_name")
        self.assertFalse(cat.is_registered(), "another_name should be unregistered")

        # now mess with the subcomponents directly to test is_registered mis-match logic
        cat.register("another_name")
        unregister_pdarray_by_name("another_name.codes")
        with pytest.raises(RegistrationError):
            cat.is_registered()

    def test_attach_weak_binding(self):
        """
        Ultimately pdarrayclass issues delete calls to the server when a bound object goes out of scope,
        if you bind to a server object more than once and one of those goes out of scope it affects
        all other references to it.
        """
        cleanup()
        a = ak.ones(3, dtype=ak.int64).register("a_reg")
        self.assertTrue(str(a), "Expected to pass")
        b = ak.attach_pdarray("a_reg")
        b.unregister()
        b = None  # Force out of scope
        with self.assertRaises(RuntimeError):
            str(a)

    def test_series_register_attach(self):
        ar_tuple = (ak.arange(5), ak.arange(5))
        s = ak.Series(ar_tuple)

        # At this time, there is no unregister() in Series. Register one piece to check partial
        # registration
        s.values.register("seriesTest_values")
        with self.assertWarns(UserWarning):
            s.is_registered()
        # Unregister values pdarray
        s.values.unregister()

        self.assertFalse(s.is_registered())

        s.register("seriesTest")
        self.assertTrue(s.is_registered())

        ak.clear()
        s2 = Series.attach("seriesTest")
        self.assertListEqual(s2.values.to_list(), s.values.to_list())
        sEq = s2.index == s.index
        self.assertTrue(all(sEq.to_ndarray()))

    def test_strings_groupby_attach(self):
        s = ak.array(["abc", "123", "abc"])
        sGroup = ak.GroupBy(s)
        sGroup.register("stringsTest")
        ak.clear()
        sAttach = ak.GroupBy.attach("stringsTest")

        # Verify the attached GroupBy's components equal the original components
        self.assertListEqual(sGroup.keys.to_list(), sAttach.keys.to_list())
        self.assertListEqual(sGroup.permutation.to_list(), sAttach.permutation.to_list())
        self.assertListEqual(sGroup.segments.to_list(), sAttach.segments.to_list())
        self.assertListEqual(sGroup.unique_keys.to_list(), sAttach.unique_keys.to_list())

        self.assertIsInstance(sAttach.keys, ak.Strings)
        self.assertIsInstance(sAttach.permutation, ak.pdarray)
        self.assertIsInstance(sAttach.segments, ak.pdarray)
        self.assertIsInstance(sAttach.unique_keys, ak.Strings)

    def test_string_property_accessor(self):
        # Verify s can be attached then accessed
        cleanup()
        s = ak.array(["one", "two", "three", "123"])
        s.register("sname")
        ak.clear()
        sAttach = ak.Strings.attach("sname")
        self.assertListEqual(s.to_list(), sAttach.to_list())
        s.get_bytes()
        self.assertTrue(s._bytes is not None)
        s.get_offsets()
        self.assertTrue(s._offsets is not None)
        self.assertListEqual(s.to_list(), sAttach.to_list())
        self.assertListEqual(s.get_bytes().to_list(), sAttach.get_bytes().to_list())
        self.assertListEqual(s.get_offsets().to_list(), sAttach.get_offsets().to_list())

        # Verify s can be accessed then attached
        cleanup()
        s = ak.array(["one", "two", "three", "123"])
        s.register("sname")
        ak.clear()
        s.get_offsets()
        self.assertTrue(s._offsets is not None)
        s.get_bytes()
        self.assertTrue(s._bytes is not None)
        sAttach = ak.Strings.attach("sname")
        self.assertListEqual(s.to_list(), sAttach.to_list())
        self.assertListEqual(s.get_bytes().to_list(), sAttach.get_bytes().to_list())
        self.assertListEqual(s.get_offsets().to_list(), sAttach.get_offsets().to_list())

        # Testing for registration after being accessed and being removed after unregistering s
        # Also tests for correct values in accessed arrays
        cleanup()
        s = ak.array(["one", "two", "three", "123"])
        s.register("sname")
        ak.clear()
        self.assertTrue(len(ak.list_registry()) == 1)

        sbytes = s.get_bytes()
        bytes_answers = ak.array(
            [111, 110, 101, 0, 116, 119, 111, 0, 116, 104, 114, 101, 101, 0, 49, 50, 51, 0]
        )
        self.assertListEqual(sbytes.to_list(), bytes_answers.to_list())
        self.assertTrue(len(ak.list_registry()) == 2)

        soffsets = s.get_offsets()
        offsets_answers = ak.array([0, 4, 8, 14])
        self.assertListEqual(soffsets.to_list(), offsets_answers.to_list())
        self.assertTrue(len(ak.list_registry()) == 3)

        s.unregister()
        self.assertTrue(len(ak.list_registry()) == 0)

        # Tests for unregistering each property and after clearing we can still access them
        cleanup()
        s = ak.array(["one", "two", "three", "123"])
        s.register("sname")
        sbytes = s.get_bytes()
        soffsets = s.get_offsets()
        self.assertTrue(len(ak.list_registry()) == 3)
        sbytes.unregister()
        self.assertTrue(len(ak.list_registry()) == 2)
        self.assertTrue(sbytes.name not in ak.list_registry())
        soffsets.unregister()
        self.assertTrue(len(ak.list_registry()) == 1)
        self.assertTrue(soffsets.name not in ak.list_registry())

        ak.clear()
        sbytes = s.get_bytes()
        soffsets = s.get_offsets()
        self.assertTrue(len(ak.list_registry()) == 3)
        self.assertTrue(sbytes.name in ak.list_registry())
        self.assertTrue(soffsets.name in ak.list_registry())

        # Tests that s does not get registered if a is accessed
        cleanup()
        s = ak.array(["one", "two", "three", "123"])
        self.assertTrue(len(ak.list_registry()) == 0)
        s.get_bytes()
        self.assertTrue(len(ak.list_registry()) == 0)
        s.get_offsets()
        self.assertTrue(len(ak.list_registry()) == 0)

        # Test to ensure we do not create a duplicate pdarrays after repeated accessing
        cleanup()
        s = ak.array(["one", "two", "three", "123"])
        s.get_bytes()
        self.assertTrue(len(ak.list_symbol_table()) == 2)
        s.get_offsets()
        self.assertTrue(len(ak.list_symbol_table()) == 3)
        s.get_offsets()
        self.assertTrue(len(ak.list_symbol_table()) == 3)

    def test_pdarray_groupby_attach(self):
        a = ak.randint(0, 10, 10)
        aGroup = ak.GroupBy(a)
        aGroup.register("pdarray_test")
        ak.clear()
        aAttach = ak.GroupBy.attach("pdarray_test")

        # Verify the attached GroupBy's components equal the original components
        self.assertListEqual(aGroup.keys.to_list(), aAttach.keys.to_list())
        self.assertListEqual(aGroup.permutation.to_list(), aAttach.permutation.to_list())
        self.assertListEqual(aGroup.segments.to_list(), aAttach.segments.to_list())
        self.assertListEqual(aGroup.unique_keys.to_list(), aAttach.unique_keys.to_list())

        self.assertIsInstance(aAttach.keys, ak.pdarray)
        self.assertIsInstance(aAttach.permutation, ak.pdarray)
        self.assertIsInstance(aAttach.segments, ak.pdarray)
        self.assertIsInstance(aAttach.unique_keys, ak.pdarray)

    def test_categorical_groupby_attach(self):
        c = ak.array(["abc", "123", "abc"])
        cat = ak.Categorical(c)
        catGroup = ak.GroupBy(cat)
        catGroup.register("categorical_test")
        ak.clear()
        catAttach = ak.GroupBy.attach("categorical_test")

        # Verify the attached GroupBy's components equal the original components
        self.assertListEqual(catGroup.keys.to_list(), catAttach.keys.to_list())
        self.assertListEqual(catGroup.permutation.to_list(), catAttach.permutation.to_list())
        self.assertListEqual(catGroup.segments.to_list(), catAttach.segments.to_list())
        self.assertListEqual(catGroup.unique_keys.to_list(), catAttach.unique_keys.to_list())

        self.assertIsInstance(catAttach.keys, ak.Categorical)
        self.assertIsInstance(catAttach.permutation, ak.pdarray)
        self.assertIsInstance(catAttach.segments, ak.pdarray)
        self.assertIsInstance(catAttach.unique_keys, ak.Categorical)

    def test_sequence_groupby_attach(self):
        a = ak.randint(0, 10, 11)
        b = ak.array(["The", "ants", "go", "marching", "one", "by", "one", ",", "hurrah", ",", "hurrah"])
        c = ak.Categorical(b)
        lx = [a, b, c]
        group = ak.GroupBy(lx)
        group.register("sequenceTest")
        ak.clear()
        seqAttach = ak.GroupBy.attach("sequenceTest")

        # Verify the attached GroupBy's components equal the original components for each key
        # in the sequence
        self.assertListEqual(group.keys[0].to_list(), seqAttach.keys[0].to_list())
        self.assertListEqual(group.keys[1].to_list(), seqAttach.keys[1].to_list())
        self.assertListEqual(group.keys[2].to_list(), seqAttach.keys[2].to_list())
        self.assertListEqual(group.unique_keys[0].to_list(), seqAttach.unique_keys[0].to_list())
        self.assertListEqual(group.unique_keys[1].to_list(), seqAttach.unique_keys[1].to_list())
        self.assertListEqual(group.unique_keys[2].to_list(), seqAttach.unique_keys[2].to_list())
        self.assertListEqual(group.permutation.to_list(), seqAttach.permutation.to_list())
        self.assertListEqual(group.segments.to_list(), seqAttach.segments.to_list())

        # Verify the attached GroupBy preserved the type of each key
        self.assertIsInstance(seqAttach.keys[0], ak.pdarray)
        self.assertIsInstance(seqAttach.keys[1], ak.Strings)
        self.assertIsInstance(seqAttach.keys[2], ak.Categorical)
        self.assertIsInstance(seqAttach.unique_keys[0], ak.pdarray)
        self.assertIsInstance(seqAttach.unique_keys[1], ak.Strings)
        self.assertIsInstance(seqAttach.unique_keys[2], ak.Categorical)
        self.assertIsInstance(seqAttach.permutation, ak.pdarray)
        self.assertIsInstance(seqAttach.segments, ak.pdarray)

    def test_groupby_register(self):
        a = ak.randint(0, 10, 11)
        b = ak.array(["The", "ants", "go", "marching", "one", "by", "one", ",", "hurrah", ",", "hurrah"])
        c = ak.Categorical(b)

        # New variable declarations for sequence
        seqA = ak.randint(0, 10, 11)
        seqB = ak.array(
            ["The", "ants", "go", "marching", "one", "by", "one", ",", "hurrah", ",", "hurrah"]
        )
        seqC = ak.Categorical(seqB)
        seq = [seqA, seqB, seqC]
        groupA = ak.GroupBy(a)
        groupB = ak.GroupBy(b)
        groupC = ak.GroupBy(c)
        groupL = ak.GroupBy(seq)

        groupA.register("pdarray_unregister")
        groupB.register("strings_unregister")
        groupC.register("categorical_unregister")
        groupL.register("sequence_unregister")

        self.assertTrue(groupA.is_registered())
        self.assertTrue(groupB.is_registered())
        self.assertTrue(groupC.is_registered())
        self.assertTrue(groupL.is_registered())

        # Test self.unregister
        groupA.unregister()
        groupB.unregister()

        # Test unregister_groupby_by_name
        ak.GroupBy.unregister_groupby_by_name("categorical_unregister")
        ak.GroupBy.unregister_groupby_by_name("sequence_unregister")

        self.assertFalse(groupA.is_registered())
        self.assertFalse(groupB.is_registered())
        self.assertFalse(groupC.is_registered())
        self.assertFalse(groupL.is_registered())

    def test_dataframe_register(self):
        # Create DataFrame
        username = ak.array(["Alice", "Bob", "Alice", "Carol", "Bob", "Alice"])
        userid = ak.array([111, 222, 111, 333, 222, 111])
        item = ak.array([0, 0, 1, 1, 2, 0])
        day = ak.array([5, 5, 6, 5, 6, 6])
        amount = ak.array([0.5, 0.6, 1.1, 1.2, 4.3, 0.6])
        index = ak.Index.factory(ak.array(["One", "Two", "Three", "Four", "Five", "Six"]))
        df = ak.DataFrame(
            {"userName": username, "userID": userid, "item": item, "day": day, "amount": amount}, index
        )

        # Register DataFrame with name 'DataFrame_test'
        df.register("DataFrame_test")
        self.assertTrue(df.is_registered())
        ak.clear()

        # Attach registered DataFrame 'DataFrame_test' into variable dfa and assert the original and
        # attached versions of the DataFrame are equal
        dfa = ak.DataFrame.attach("DataFrame_test")
        self.assertTrue(df.to_pandas().equals(dfa.to_pandas()))

        # Unregister a single component of the DataFrame to assert a warning is raised when not all
        # expected components of the DataFrame are registered
        ak.pdarrayclass.unregister_pdarray_by_name("df_index_DataFrame_test_key")
        with self.assertWarns(UserWarning):
            df.is_registered()

        # Unregister the DataFrame and assert that it has been unregistered completely
        df.unregister()
        self.assertFalse(df.is_registered())

    def test_segarray_register_attach(self):
        a = [1, 2, 3]
        b = [6, 7, 8]

        segarr = ak.SegArray(ak.array([0, len(a)]), ak.array(a + b))
        # register the seg array
        segarr.register("segarrtest")
        ak.clear()
        segarr_2 = ak.SegArray.attach("segarrtest")

        self.assertEqual(segarr.size, segarr_2.size)
        self.assertListEqual(segarr.lengths.to_list(), segarr_2.lengths.to_list())
        self.assertListEqual(segarr.segments.to_list(), segarr_2.segments.to_list())
        self.assertListEqual(segarr.values.to_list(), segarr_2.values.to_list())

        # Verify is_registered
        self.assertTrue(segarr.is_registered())
        segarr.unregister()
        self.assertFalse(segarr.is_registered())

    def test_segarray_unregister_by_name(self):
        a = [1, 2, 3]
        b = [6, 7, 8]

        segarr = ak.SegArray(ak.array([0, len(a)]), ak.array(a + b))
        # register the seg array
        segarr.register("segarr_unreg_name_test")
        ak.clear()

        # Verify is_registered
        self.assertTrue(segarr.is_registered())

        # Unregister all components
        ak.SegArray.unregister_segarray_by_name("segarr_unreg_name_test")

        # Verify no registered components remain
        self.assertFalse(segarr.is_registered())

    def test_symentry_cleanup(self):
        cleanup()
        pda = ak.arange(10)
        self.assertTrue(len(ak.list_symbol_table()) > 0)
        pda = None
        self.assertEqual(len(ak.list_symbol_table()), 0)

        s = ak.array(["a", "b", "c"])
        self.assertTrue(len(ak.list_symbol_table()) > 0)
        s = None
        self.assertEqual(len(ak.list_symbol_table()), 0)

        cat = ak.Categorical(ak.array(["a", "b", "c"]))
        self.assertTrue(len(ak.list_symbol_table()) > 0)
        cat = None
        self.assertEqual(len(ak.list_symbol_table()), 0)

        seg = ak.SegArray(
            ak.array([0, 6, 8]), ak.array([10, 11, 12, 13, 14, 15, 20, 21, 30, 31, 32, 33])
        )
        self.assertTrue(len(ak.list_symbol_table()) > 0)
        seg = None
        self.assertEqual(len(ak.list_symbol_table()), 0)

        str_seg = ak.SegArray(
            ak.array([0, 6, 8]), ak.array([10, 11, 12, 13, 14, 15, 20, 21, 30, 31, 32, 33])
        )
        self.assertTrue(len(ak.list_symbol_table()) > 0)
        str_seg = None
        self.assertEqual(len(ak.list_symbol_table()), 0)

        g = ak.GroupBy(
            [ak.arange(3), ak.array(["a", "b", "c"]), ak.Categorical(ak.array(["a", "b", "c"]))]
        )
        self.assertTrue(len(ak.list_symbol_table()) > 0)
        g = None
        self.assertEqual(len(ak.list_symbol_table()), 0)

        d = ak.DataFrame(
            {
                "pda": ak.arange(3),
                "s": ak.array(["a", "b", "c"]),
                "cat": ak.Categorical(ak.array(["a", "b", "c"])),
                "seg": ak.SegArray(
                    ak.array([0, 6, 8]), ak.array([10, 11, 12, 13, 14, 15, 20, 21, 30, 31, 32, 33])
                ),
            }
        )
        self.assertTrue(len(ak.list_symbol_table()) > 0)
        d = None
        self.assertEqual(len(ak.list_symbol_table()), 0)


def cleanup():
    ak.clear()
    for registered_name in ak.list_registry():
        ak.unregister_pdarray_by_name(registered_name)
    ak.clear()
